FROM python:3.7.10 AS image-base  
COPY requirements.txt /data/requirements.txt
RUN pip config set global.index-url "https://mirrors.sjtug.sjtu.edu.cn/pypi/web/simple" && pip config set global.index-url "https://mirrors.sjtug.sjtu.edu.cn/pypi/web/simple" && pip install  --user  --no-cache-dir -r /data/requirements.txt

FROM python:3.7.10-alpine

COPY . /data/
COPY --from=image-base /root/.local /root/.local

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.sjtug.sjtu.edu.cn/g' /etc/apk/repositories && echo 'https://mirrors.sjtug.sjtu.edu.cn/alpine/edge/testing'>>/etc/apk/repositories && rm -rf /root/.cache && apk add --allow-untrusted  tzdata && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && apk del tzdata 

WORKDIR /data/
CMD ["python3","etcd-backuper.py"]