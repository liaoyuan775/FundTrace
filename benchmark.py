from datetime import datetime, timedelta
from time import perf_counter
from app.analysis.core import build_graph
from app.models import TransactionRecord

records=[]
for i in range(100_000):
    records.append(TransactionRecord(transaction_id=f"B{i}",transaction_time=datetime(2026,1,1)+timedelta(seconds=i),payer_account=f"A{i%500}",payer_name=f"账户{i%500}",payee_account=f"A{(i*7+13)%500}",payee_name=f"账户{(i*7+13)%500}",amount=100+(i%1000),review_status="confirmed"))
start=perf_counter();graph=build_graph(records);elapsed=perf_counter()-start
print({"transactions":len(records),"nodes":len(graph["nodes"]),"edges":len(graph["edges"]),"seconds":round(elapsed,3)})
assert elapsed < 10

