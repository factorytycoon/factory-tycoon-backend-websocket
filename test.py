import redis

r = redis.Redis(host='175.114.229.158', port=6379, password="pass", decode_responses=True)
for msg in r.xrange('pending:mongodb_stream', min='-', max='+'):
    print(msg)