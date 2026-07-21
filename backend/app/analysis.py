from collections import defaultdict, deque

from .ingestion import canonical_records
from .models import AttributionEdge, AttributionResult, TransactionRecord


RISK_KEYWORDS = ("涉诈", "博彩", "虚假", "资金拆分", "任务佣金", "跑分", "洗钱")


def _risk_factor(code: str, name: str, score: int, evidence: str) -> dict:
    return {"code": code, "name": name, "score": score, "evidence": evidence}


def count_rapid_transfers(incoming: list[TransactionRecord], outgoing: list[TransactionRecord]) -> int:
    incoming=sorted(incoming,key=lambda t:t.transaction_time);outgoing=sorted(outgoing,key=lambda t:t.transaction_time)
    count=0;left=0
    for target in outgoing:
        while left<len(incoming) and (target.transaction_time-incoming[left].transaction_time).total_seconds()>1800:left+=1
        index=left
        while index<len(incoming) and incoming[index].transaction_time<=target.transaction_time:
            count+=1;index+=1
    return count


def has_split_transfer(outgoing: list[TransactionRecord]) -> bool:
    outgoing=sorted(outgoing,key=lambda t:t.transaction_time);left=0
    for right,target in enumerate(outgoing):
        while (target.transaction_time-outgoing[left].transaction_time).total_seconds()>3600:left+=1
        if right-left+1>=3:return True
    return False


def score_account_risk(related: list[TransactionRecord], incoming: list[TransactionRecord], outgoing: list[TransactionRecord]) -> dict:
    factors=[]
    rapid_count=count_rapid_transfers(incoming,outgoing)
    if rapid_count:
        factors.append(_risk_factor("rapid_transfer","快速转出",20,f"入账后30分钟内转出 {rapid_count} 组"))
    incoming_amount=sum(t.amount for t in incoming);outgoing_amount=sum(t.amount for t in outgoing)
    pass_ratio=min(incoming_amount,outgoing_amount)/(incoming_amount or 1)
    if pass_ratio>=0.6:
        factors.append(_risk_factor("pass_through","高资金穿透率",25,f"流出/流入穿透率 {pass_ratio:.0%}"))
    elif pass_ratio>=0.3:
        factors.append(_risk_factor("pass_through","中等资金穿透率",15,f"流出/流入穿透率 {pass_ratio:.0%}"))
    counterparties={t.payer_account for t in incoming}|{t.payee_account for t in outgoing}
    if len(counterparties)>=4:
        factors.append(_risk_factor("multiple_counterparties","多收多转",10,f"关联对手账户 {len(counterparties)} 个"))
    if has_split_transfer(outgoing):
        factors.append(_risk_factor("split_transfer","短时分拆",20,"60分钟内向至少3个下游转出"))
    return_records=[t for t in related if "回流" in t.summary]
    if return_records:
        factors.append(_risk_factor("return_flow","资金回流",15,f"发现回流流水 {len(return_records)} 笔"))
    risky_records=[t for t in related if any(keyword in f"{t.summary} {t.channel}" for keyword in RISK_KEYWORDS)]
    if risky_records:
        factors.append(_risk_factor("risky_signal","风险语义命中",10,f"摘要或渠道命中风险词 {len(risky_records)} 笔"))
    score=min(100,sum(factor["score"] for factor in factors))
    level="高风险" if score>=70 else "中风险" if score>=40 else "低风险"
    return {"score":score,"level":level,"factors":factors,"method":"internal_rules_v1"}


def _result(method: str, transactions: list[TransactionRecord], amounts: list[float], victim_amount: float) -> AttributionResult:
    edges=[AttributionEdge(transaction_id=t.transaction_id,from_account=t.payer_account,to_account=t.payee_account,original_amount=t.amount,attributed_amount=round(a,2)) for t,a in zip(transactions,amounts) if a>0]
    total=round(min(victim_amount,sum(item.attributed_amount for item in edges)),2)
    return AttributionResult(method=method,total_attributed=total,remaining_amount=round(max(0,victim_amount-total),2),edges=edges)


def attribute_mixed_funds(transactions: list[TransactionRecord], source_account: str, victim_amount: float, preexisting_balance: float) -> dict[str,AttributionResult]:
    outgoing=sorted((t for t in transactions if t.payer_account==source_account),key=lambda t:t.transaction_time)
    remaining=victim_amount; fifo=[]
    for t in outgoing:
        value=min(t.amount,remaining); fifo.append(value); remaining-=value
    original=preexisting_balance; conservative=[]; remaining=victim_amount
    for t in outgoing:
        ordinary=min(original,t.amount); original-=ordinary
        value=min(max(0,t.amount-ordinary),remaining); conservative.append(value); remaining-=value
    total_out=sum(t.amount for t in outgoing); ratio=victim_amount/(victim_amount+preexisting_balance) if victim_amount+preexisting_balance else 0
    proportional=[]; remaining=victim_amount
    for t in outgoing:
        value=min(t.amount*ratio,remaining); proportional.append(value); remaining-=value
    if remaining>0 and proportional:
        proportional[-1]+=remaining
    possible=[]; remaining=victim_amount
    for t in sorted(outgoing,key=lambda t:t.amount,reverse=True):
        value=min(t.amount,remaining); possible.append(value); remaining-=value
    possible_map={t.transaction_id:a for t,a in zip(sorted(outgoing,key=lambda t:t.amount,reverse=True),possible)}
    return {
        "fifo":_result("fifo",outgoing,fifo,victim_amount),
        "conservative":_result("conservative",outgoing,conservative,victim_amount),
        "possible_max":_result("possible_max",outgoing,[possible_map[t.transaction_id] for t in outgoing],victim_amount),
        "proportional":_result("proportional",outgoing,proportional,victim_amount),
    }


def build_graph(records: list[TransactionRecord], query: str="", min_amount: float=0, direction: str="all", channel: str="", bank: str="", region: str="", date_from: str="", date_to: str="") -> dict:
    records=canonical_records(records)
    query=query.lower().strip()
    filtered=[t for t in records if t.amount>=min_amount and (not query or query in " ".join([t.serial_number,t.payer_account,t.payer_name,t.payee_account,t.payee_name,t.summary]).lower()) and (direction=="all" or (direction=="return" and "回流" in t.summary) or (direction=="forward" and "回流" not in t.summary)) and (not channel or t.channel==channel) and (not bank or bank in t.payer_bank or bank in t.payee_bank) and (not region or t.region==region) and (not date_from or t.transaction_time.date().isoformat()>=date_from) and (not date_to or t.transaction_time.date().isoformat()<=date_to)]
    nodes={}; edge_map={};related_by_account=defaultdict(list);incoming_records=defaultdict(list);outgoing_records=defaultdict(list)
    incoming=defaultdict(float); outgoing=defaultdict(float)
    for t in filtered:
        incoming[t.payee_account]+=t.amount; outgoing[t.payer_account]+=t.amount
        related_by_account[t.payer_account].append(t);related_by_account[t.payee_account].append(t)
        incoming_records[t.payee_account].append(t);outgoing_records[t.payer_account].append(t)
        for account,name,bank in ((t.payer_account,t.payer_name,t.payer_bank),(t.payee_account,t.payee_name,t.payee_bank)):
            nodes.setdefault(account,{"id":account,"label":name or account,"account":account,"bank":bank,"incoming":0,"outgoing":0,"risk":0})
        key=f"{t.payer_account}>{t.payee_account}"
        edge=edge_map.setdefault(key,{"id":key,"source":t.payer_account,"target":t.payee_account,"amount":0,"count":0,"transaction_ids":[],"first_transaction_time":t.transaction_time.isoformat()})
        edge["amount"]+=t.amount; edge["count"]+=1; edge["transaction_ids"].append(t.transaction_id)
        edge["first_transaction_time"]=min(edge["first_transaction_time"],t.transaction_time.isoformat())
    for account,node in nodes.items():
        node["incoming"]=incoming[account]; node["outgoing"]=outgoing[account]
        assessment=score_account_risk(related_by_account[account],incoming_records[account],outgoing_records[account])
        node["risk"]=assessment["score"];node["risk_level"]=assessment["level"];node["risk_factors"]=assessment["factors"]
    highest=max(nodes.values(),key=lambda item:item["risk"],default=None)
    risk_summary={"score":highest["risk"] if highest else 0,"level":highest["risk_level"] if highest else "低风险","account_id":highest["id"] if highest else None,"account_label":highest["label"] if highest else "无","method":"internal_rules_v1","disclaimer":"内部规则风险提示，不构成犯罪事实或司法认定。"}
    return {"nodes":list(nodes.values()),"edges":list(edge_map.values()),"transaction_count":len(filtered),"total_amount":sum(t.amount for t in filtered),"risk_summary":risk_summary}


def shortest_path(records: list[TransactionRecord], start: str, end: str) -> list[str]:
    graph=defaultdict(set)
    for t in records: graph[t.payer_account].add(t.payee_account)
    queue=deque([(start,[start])]); seen={start}
    while queue:
        node,path=queue.popleft()
        if node==end:return path
        for nxt in graph[node]:
            if nxt not in seen: seen.add(nxt);queue.append((nxt,path+[nxt]))
    return []


def trace_network(records: list[TransactionRecord], start: str, end: str = "", hops: int = 3) -> dict:
    forward=defaultdict(set); reverse=defaultdict(set)
    for t in records:
        forward[t.payer_account].add(t.payee_account);reverse[t.payee_account].add(t.payer_account)
    def walk(graph):
        seen={start};frontier={start}
        for _ in range(max(0,min(hops,8))):
            frontier={nxt for node in frontier for nxt in graph[node] if nxt not in seen}
            seen.update(frontier)
            if not frontier:break
        return sorted(seen)
    cycles=[]
    def dfs(node,path):
        if len(path)>hops+2:return
        for nxt in sorted(forward[node]):
            if nxt==start and len(path)>1:
                cycle=path+[start]
                if cycle not in cycles:cycles.append(cycle)
            elif nxt not in path:dfs(nxt,path+[nxt])
    dfs(start,[start])
    return {"start":start,"end":end,"hops":hops,"upstream":walk(reverse),"downstream":walk(forward),"shortest_path":shortest_path(records,start,end) if end else [],"cycles":cycles[:50]}
