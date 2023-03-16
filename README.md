
ETCDCTL_API=3 etcdctl --endpoints=https://10.9.171.53:2379 --cacert=/etc/ssl/etcd/ssl/ca.pem --cert=/etc/ssl/etcd/ssl/member-k8s-master-1.pem --key=/etc/ssl/etcd/ssl/member-k8s-master-1-key.pem snapshot save /tmp/1.db
ETCDCTL_API=3 etcdctl --endpoints=https://10.9.171.215:2379 --cacert=/etc/ssl/etcd/ssl/ca.pem --cert=/etc/ssl/etcd/ssl/member-k8s-master-1.pem --key=/etc/ssl/etcd/ssl/member-k8s-master-1-key.pem snapshot save /tmp/2.db
ETCDCTL_API=3 etcdctl --endpoints=https://10.9.171.134:2379 --cacert=/etc/ssl/etcd/ssl/ca.pem --cert=/etc/ssl/etcd/ssl/member-k8s-master-1.pem --key=/etc/ssl/etcd/ssl/member-k8s-master-1-key.pem snapshot save /tmp/3.db

- precheck
  - check config
- backup all etcd
- upload backupdb to s3