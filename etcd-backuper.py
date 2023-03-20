import sys
import boto3
import time
import logging
import subprocess
import json
import os
import threading
from time import sleep
from configparser import ConfigParser
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from botocore.exceptions import ClientError
from requests import Session

# Setup a log formatter
formatter = logging.Formatter(
    "%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s : %(message)s")
# Setup a log file handler and set level/formater
logFile = RotatingFileHandler(
    filename="./logs/runtime.log", maxBytes=1024*1024*20, backupCount=10)

logFile.setFormatter(formatter)
# Setup a log console handler and set level/formater
logConsole = logging.StreamHandler()
logConsole.setFormatter(formatter)
# Setup a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logFile)
logger.addHandler(logConsole)


class ProgressPercentage(object):
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self.percentage = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        # To simplify, assume this is hooked up to a single filename
        self._seen_so_far += bytes_amount
        if self.percentage != int((self._seen_so_far / self._size) * 100) and int((self._seen_so_far / self._size) * 100) % 10 == 0:
            self.percentage = int((self._seen_so_far / self._size) * 100)
            logger.info("Uploading: %s [%.3d%%] %.2f/%.2f MB" % (self._filename,
                        self.percentage,self._seen_so_far/1024/1024, self._size/1024/1024))


class EtcdBackuper:
    def __init__(self) -> None:
        config = ConfigParser()
        config.read('config.ini')
        self.clusterName = config['cluster']['name']
        self.feishuAppId = config['cluster']['feishuAppId']
        self.feishuAppSecret = config['cluster']['feishuAppSecret']
        self.groupsName = config['cluster']['groupsName']
        self.s3_endpoint = config['s3']['S3_ENDPOINT']
        self.s3_bucket = config['s3']['S3_BUCKET']
        self.s3_accesskey = config['s3']['S3_ACCESSKEY']
        self.s3_secretkey = config['s3']['S3_SECRETKEY']
        self.etcdEdnpoints = config['etcd']
        try:
            currentDatetime = datetime.today().strftime("%Y-%m-%d-%H:%M:%S")
            self.s = Session()
            r = self.s.post(
                'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                json={
                    'app_id': self.feishuAppId,
                    'app_secret': self.feishuAppSecret
                },
                verify=True,
                timeout=5
            ).json()
            tenant_access_token = r['tenant_access_token']
            headers = {"Authorization": "Bearer %s" % (tenant_access_token)}
            self.s.headers.update(headers)
            logger.info("Current date time: %s" % currentDatetime)
        except Exception as e:
            logger.exception('Exception:')
            logger.error(e)
            sys.exit(1)

        self.s3 = boto3.client(
            's3',
            endpoint_url='https://%s' % self.s3_endpoint,
            aws_access_key_id=self.s3_accesskey,
            aws_secret_access_key=self.s3_secretkey)

    def uploadToS3(self, dumpFilePath):
        try:
            year = time.strftime("%Y")
            month = time.strftime("%m")
            day = time.strftime("%d")
            file = dumpFilePath.split('/')[-1]
            key = '%s/%s/%s/%s/%s' % (self.clusterName, year, month, day, file)
            self.s3.upload_file(dumpFilePath, self.s3_bucket, key, ExtraArgs={
                'StorageClass': 'DEEP_ARCHIVE'}, Callback=ProgressPercentage(dumpFilePath))
            return True, key
        except ClientError as e:
            logging.error(e)
            return False, e

    def run_command(self, command, cwd=None, timeout=180):
        try:
            logger.info('[COMMAND] RUN CMD: [%s], CWD: [%s], TIMEOUT: [%s]' %
                        (command, cwd, timeout))
            popen = subprocess.Popen(
                command,
                cwd=cwd,
                close_fds=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10000,
                shell=True
            )
            end_time = datetime.now() + timedelta(seconds=timeout)
            while True:
                stdout, stderr = popen.communicate()
                stdout_text = (stdout.decode('utf8')).strip()
                stderr_text = (stderr.decode('utf8')).strip()
                try:
                    print(stderr_text)
                    logger.info(stdout_text)
                except Exception as e:
                    pass

                if popen.poll() is not None:
                    break

                sleep(0.1)
                if end_time <= datetime.now():
                    popen.kill()
                    logger.critical('[COMMAND] EXEC TIMEOUT')
                    return False, None, None

            if popen.returncode > 0:
                logger.info('[COMMAND] FAILED:[%s], CODE:[%s], \nSTDOUT:[\n%s\n]\nSTDERR:[\n%s\n]' % (
                    command, popen.returncode, stdout_text, stderr_text))

                return False
            else:
                logger.info('[COMMAND] SUCCESS:[%s], CODE:[%s]' %
                            (command, popen.returncode))
                return True, stdout_text
        except Exception as e:
            logger.exception('[COMMAND] EXCEPTION:[%s]:' % (command))
            return False

    def sendToWhichGroups(self):
        try:
            r = self.s.get(
                'https://open.feishu.cn/open-apis/im/v1/chats', timeout=5)
            if r.json()['code'] == 0:
                joinedGroupsDic = {}
                for chatGroup in r.json()['data']['items']:
                    joinedGroupsDic[chatGroup['chat_id']] = chatGroup['name']
                logger.info('Bot joined Group Dic: %s' % (joinedGroupsDic))
                self.joinedGroupsDic = joinedGroupsDic
                print(joinedGroupsDic)

            else:
                logger.error('Get: %s' % r.url)
                raise Exception(
                    'getAllBotJoinedGroup Failed, Response: %s' % (r.json()))

            sendingGroups = {}
            try:
                groupsName = self.groupsName.split(',')
                logger.info(
                    'Found Group List: %s' % (groupsName))
                for groupName in self.joinedGroupsDic:
                    if self.joinedGroupsDic[groupName] in groupsName:
                        sendingGroups[groupName] = self.joinedGroupsDic[groupName]
                        logger.info('Found group: %s' % (groupName))
                    else:
                        pass

            except Exception as e:
                logger.exception('Exception:')
                logger.error(e)
                sys.exit(1)

            finally:
                return sendingGroups

        except Exception as e:
            logger.exception('Exception:')
            logger.error(e)
            sys.exit(1)

    def sendMessages(self, resultDic):

        # resultDic = {
        #     'clusterName': self.clusterName,
        #     'success': [],
        #     'failure': []
        # }
        # resultDic['success'].append(
        #                     (endpointName, endpointAddr, '%s.%s/%s' % (self.s3_bucket, self.s3_endpoint, key)))
        # resultDic['failure'].append(
        #                     (endpointName, endpointAddr, str(key)))

        if resultDic['failure'].__len__() == 0:
            template = 'green'
        else:
            template = 'red'

        successStr = ""
        for result in resultDic['success']:
            endpointName = result[0]
            endpointAddr = result[1]
            key = result[2]
            successStr = successStr + \
                "**%s**: %s > %s\n" % (endpointName, endpointAddr, key)

        failureStr = ""
        for result in resultDic['failure']:
            endpointName = result[0]
            endpointAddr = result[1]
            key = result[2]
            failureStr = failureStr + \
                "**%s**: %s > %s\n" % (endpointName, endpointAddr, key)

        devmsgContent = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": template,
                "title": {
                    "content": "集群: %s ETCD 备份结果" % (self.clusterName),
                    "tag": "plain_text"
                }
            },
            "elements": [
                {
                    "tag": "hr"
                },
                {
                    "tag": "markdown",
                    "content": "**🎉  备份成功:**\n%s" % (successStr)
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "markdown",
                    "content": "[**>>> 查看备份 <<<**](https://console.ucloud.cn/ufile/ufile/detail?id=%s&tab=overview)" % self.s3_bucket
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "✅ 完成时间: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"))
                        }
                    ]
                }
            ]
        }


        if failureStr != "":
            failureItem ={
                "tag": "markdown",
                "content": "**🔴  备份失败:**\n%s" % (failureStr)
            }
            hr = {
                "tag": "hr"
            },
            devmsgContent['elements'].insert(2,hr)
            devmsgContent['elements'].insert(2,failureItem)
        

        sendingGroups = self.sendToWhichGroups()
        for receive_id in sendingGroups:
            try:

                msgJson = {
                    "receive_id": "%s" % (receive_id),
                    "msg_type": "interactive",
                    "content": json.dumps(devmsgContent)
                }

                r = self.s.post(
                    'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id', timeout=5, json=msgJson)
                if r.json()['code'] == 0:
                    logger.info('[MESSAGE] Send to Group success: "%s"' %
                                (sendingGroups[receive_id]))
                else:
                    logger.error('[MESSAGE] Post Group: %s' % r.json())
            except:
                logger.exception('[MESSAGE] Exception:')
                logger.error(
                    'Send message to Group failed: %s' % (sendingGroups))

    def run(self):
        resultDic = {
            'clusterName': self.clusterName,
            'success': [],
            'failure': []
        }
        for endpoint in self.etcdEdnpoints:
            try:
                endpointName = endpoint
                endpointAddr = self.etcdEdnpoints[endpoint]
                logger.info('[BACKUP] [START] Backup: %s, ETCD Address: %s' %
                            (endpointName, endpointAddr))

                timeStr = time.strftime("%Y-%m-%d-%H-%M-%S")
                filename = '%s-%s.db' % (timeStr, endpointName)
                command = 'ETCDCTL_API=3 ./etcdctl --endpoints=%s --cacert=./certs/ca.pem --cert=./certs/cert.pem --key=./certs/cert.key snapshot save ./dumps/%s' % (
                    endpointAddr, filename)

                success, stdout_text = self.run_command(command=command)

                if success == True and 'Snapshot saved at' in stdout_text:
                    dumpFilePath = './dumps/%s' % (filename)
                    logger.info('[UPLOAD] Uploading file: %s' % (dumpFilePath))
                    success, key = self.uploadToS3(dumpFilePath)
                    if success == True:
                        logger.info('[UPLOAD] [SUCCESS] Upload finished: %s.%s/%s' %
                                    (self.s3_bucket, self.s3_endpoint, key))
                        os.remove(dumpFilePath)
                        resultDic['success'].append(
                            (endpointName, endpointAddr, '%s.%s/%s' % (self.s3_bucket, self.s3_endpoint, key)))
                        logger.info('[UPLOAD] Cleared file: %s' % dumpFilePath)
                    else:
                        logger.error('[UPLOAD] Upload failed')
                        resultDic['failure'].append(
                            (endpointName, endpointAddr, str(key)))

                logger.info('[BACKUP] [SUCCESS] Backup: %s, ETCD Address: %s' %
                            (endpointName, endpointAddr))
            except Exception as e:
                logger.exception('Stack: \n')
                logger.critical('[BACKUP] [FAILED] Backup: %s, ETCD Address: %s' % (
                    endpointName, endpointAddr))
                resultDic['failure'].append(
                    (endpointName, endpointAddr, str(e)))
                continue

        self.sendMessages(resultDic)


etcdbackuper = EtcdBackuper()
etcdbackuper.run()