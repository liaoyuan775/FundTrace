from datetime import datetime, timedelta

from .models import CaseRecord, TransactionRecord, Victim


NAMES = [
    "王海涛","李倩","陈志强","周晓燕",
    "张伟","刘芳","陈强","杨敏","赵磊","周婷","吴刚","孙丽","胡军","朱静","高峰","林娜",
    "王志鹏","李晓梅","郭海波","马俊","何丽","黄凯","罗丹","宋杰","郑敏","谢勇","彭娟","唐斌","曹雪","邓超",
    "鑫达贸易商行","瑞丰电子经营部","李建国","何志远","盛汇咨询中心","叶晨","鸿运百货商行","杜鹏","海纳网络科技","蒋欣","恒诚商务服务部","魏勇","佳信数码商行","任洁",
    "ATM-长沙解放西路","ATM-深圳华强北","银联商户-金辉珠宝","聚合支付-迅捷科技","数字资产承兑商A","数字资产承兑商B","POS商户-宏达烟酒","境外支付通道-XP"
]
BANKS=["中国工商银行长沙芙蓉支行","中国农业银行长沙天心支行","中国建设银行长沙雨花支行","中国银行长沙岳麓支行","交通银行长沙五一支行","招商银行长沙分行","中国邮政储蓄银行长沙开福支行","长沙银行星城支行","中信银行长沙分行","平安银行长沙分行"]


def demo_case() -> CaseRecord:
    return CaseRecord(name="星火专案·跨省电诈资金链",case_number="FZ-2026-0716-09",victims=[Victim(name="受害人甲",accounts=["6217000000009001"],reported_loss=50000),Victim(name="受害人乙",accounts=["6217000000009002"],reported_loss=86000)])


def demo_transactions() -> list[TransactionRecord]:
    accounts=[]
    levels=[("S",4),("A",12),("B",14),("C",14),("E",8)]
    index=0
    for prefix,count in levels:
        for i in range(1,count+1):
            accounts.append({"id":f"{prefix}{i:02d}","account":f"62{index%7+10}{index:013d}","name":NAMES[index],"bank":BANKS[index%len(BANKS)]});index+=1
    by_id={a["id"]:a for a in accounts}; source=[f"S{i:02d}" for i in range(1,5)]; l1=[f"A{i:02d}" for i in range(1,13)];l2=[f"B{i:02d}" for i in range(1,15)];l3=[f"C{i:02d}" for i in range(1,15)];exits=[f"E{i:02d}" for i in range(1,9)]
    records=[];base=datetime(2026,6,18,20,16);minute=0
    def add(src,dst,amount,memo="跨行转账"):
        nonlocal minute
        if len(records)>=118:return
        minute+=7+(len(records)%9);a=by_id[src];b=by_id[dst]
        records.append(TransactionRecord(transaction_id=f"T{len(records)+1:03d}",transaction_time=base+timedelta(minutes=minute),serial_number=f"TX20260618{100000+len(records)*7919}",payer_account=a["account"],payer_name=a["name"],payer_bank=a["bank"],payee_account=b["account"],payee_name=b["name"],payee_bank=b["bank"],amount=amount,balance_after=8000+(len(records)%11)*5300,channel=["手机银行","网上银行","超级网银","ATM转账","快捷支付"][len(records)%5],summary=memo,region=["湖南长沙","广东深圳","福建厦门","湖北武汉","广西南宁"][len(records)%5],review_status="confirmed",provenance="human_confirmed",parser_name="demo",confidence={"all":1.0}))
    for i,to in enumerate(l1):add(source[i%4],to,68000+(i%5)*13700,"涉诈入金");add(source[(i+1)%4],to,24000+(i%4)*8600,"任务佣金")
    for i,src in enumerate(l1):add(src,l2[i%14],37000+(i%6)*9200,"资金拆分");add(src,l2[(i+5)%14],18000+(i%7)*5100,"实时转账");add(src,l2[(i+9)%14],12000+(i%4)*4300,"跨行分流")
    for i,src in enumerate(l2):add(src,l3[(i*2)%14],26000+(i%5)*7600,"资金归集");add(src,l3[(i*2+3)%14],15000+(i%6)*3900,"跨行转账")
    for i,src in enumerate(l3):add(src,exits[i%8],19000+(i%6)*5800,"ATM预约取现" if i%3==0 else "商户消费")
    for i,(src,dst) in enumerate([("B12","A03"),("C10","B06"),("C04","A09"),("B02","A02"),("C14","B11"),("C06","A11")]):add(src,dst,8200+i*1700,"资金回流")
    for i,(src,dst) in enumerate([("A01","C04"),("A07","C09"),("S02","B06"),("B14","E08"),("A12","C11"),("S04","B02")]):add(src,dst,31000+i*6400,"跨层直转")
    fill=0
    while len(records)<118:add(l3[fill%14],exits[(fill*3)%8],7200+(fill%9)*3300,"快捷支付" if fill%2 else "ATM取现");fill+=1
    return records
