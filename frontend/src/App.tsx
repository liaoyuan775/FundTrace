import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BadgeCheck,
  BadgeDollarSign,
  ChevronRight,
  CircleHelp,
  Download,
  FileArchive,
  FileCheck2,
  FileSearch,
  FolderOpen,
  Gauge,
  GitBranch,
  LoaderCircle,
  Menu,
  Pause,
  Play,
  RefreshCcw,
  Search,
  ShieldAlert,
  Upload,
} from "lucide-react";
import * as api from "./api";
import {
  maximumGraphHeight,
  resizeAnalysisSplit,
} from "./analysis-split";
import GraphCanvas from "./GraphCanvas";
import { selectionForTransaction } from "./selection-state";
import type {
  CaseRecord,
  GraphData,
  Material,
  Seed,
  Transaction,
  Version,
} from "./types";

const EMPTY_GRAPH: GraphData = {
  nodes: [],
  edges: [],
  transaction_count: 0,
  total_amount: 0,
  risk_summary: {
    score: 0,
    level: "低风险",
    account_id: null,
    account_label: "无",
    method: "internal_rules_v1",
    disclaimer: "内部规则风险提示，不构成犯罪事实或司法认定。",
  },
};
const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(value);
const mask = (account: string) =>
  account.length > 8
    ? `${account.slice(0, 4)} **** **** ${account.slice(-4)}`
    : account;
const transactionSourceLabel = (
  transaction: Transaction,
  materials: Material[],
) => {
  const source = transaction.source;
  const material = materials.find(
    (item) => item.file_id === source.source_file_id,
  );
  const fileName =
    material?.relative_path ||
    material?.original_name ||
    source.source_file_id ||
    "未定位原始材料";
  const location = [
    source.page_number ? `第${source.page_number}页` : "",
    source.sheet_name ? `${source.sheet_name}工作表` : "",
    source.row_number ? `第${source.row_number}行` : "",
  ].filter(Boolean);

  return location.length ? `${fileName} · ${location.join(" · ")}` : fileName;
};
const tabs = [
  ["cases", "案件中心", FolderOpen],
  ["materials", "材料接收", Upload],
  ["review", "流水校核", FileCheck2],
  ["seeds", "涉诈起点", BadgeDollarSign],
  ["analysis", "资金研判", GitBranch],
] as const;

export default function App() {
  const [tab, setTab] = useState("analysis");
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [caseId, setCaseId] = useState("");
  const [caseInfo, setCaseInfo] = useState<CaseRecord | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [allTransactions, setAllTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [versions, setVersions] = useState<Version[]>([]);
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const [graph, setGraph] = useState<GraphData>(EMPTY_GRAPH);
  const [filters, setFilters] = useState<api.Filters>({
    query: "",
    status: "",
    minAmount: 0,
    direction: "all",
    channel: "",
    bank: "",
    region: "",
    dateFrom: "2026-06-18",
    dateTo: "2026-06-21",
    sort: "time_asc",
  });
  const [status, setStatus] = useState("");
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [attribution, setAttribution] = useState("fifo");
  const [attributionData, setAttributionData] = useState<any>(null);
  const [playing, setPlaying] = useState(false);
  const [tick, setTick] = useState(0);
  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);
  const previousActiveMaterials = useRef(0);
  const notify = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(""), 2200);
  };
  const loadCases = async () => {
    let list = await api.listCases();
    if (!list.length) {
      const demo = await api.bootstrapDemo();
      list = await api.listCases();
      setCaseId(demo.case_id);
    }
    setCases(list);
    if (!caseId && list[0]) setCaseId(list[0].case_id);
  };
  const reload = useCallback(async () => {
    if (!caseId) return;
    const active = { ...filters, status };
    const [info, ms, tx, allTx, vs, ss, g] = await Promise.all([
      api.getCase(caseId),
      api.listMaterials(caseId),
      api.getTransactions(caseId, active),
      api.getTransactions(caseId, {
        query: "",
        status: "",
        minAmount: 0,
        direction: "all",
        channel: "",
        bank: "",
        region: "",
        dateFrom: "",
        dateTo: "",
        sort: "time_asc",
      }),
      api.listVersions(caseId),
      api.listSeeds(caseId),
      api.getGraph(caseId, active),
    ]);
    setCaseInfo(info);
    setMaterials(ms);
    setTransactions(tx.items);
    setAllTransactions(allTx.items);
    setTotal(tx.total);
    setVersions(vs);
    setSeeds(ss);
    setGraph(g);
  }, [caseId, filters, status]);
  useEffect(() => {
    loadCases().catch((e) => notify(e.message));
  }, []);
  useEffect(() => {
    reload().catch((e) => notify(e.message));
  }, [reload]);
  const activeMaterialCount = materials.filter((item) =>
    ["queued", "parsing"].includes(item.status),
  ).length;
  useEffect(() => {
    if (!caseId || activeMaterialCount === 0) return;
    const timer = window.setInterval(() => {
      api.listMaterials(caseId).then((next) => {
        setMaterials(next);
        if (!next.some((item) => ["queued", "parsing"].includes(item.status))) {
          reload().catch((e) => notify(e.message));
        }
      }).catch((e) => notify(e.message));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [caseId, activeMaterialCount, reload]);
  useEffect(() => {
    if (previousActiveMaterials.current > 0 && activeMaterialCount === 0) {
      const failed = materials.filter((item) => item.status === "failed").length;
      const partial = materials.filter((item) => item.status === "partial").length;
      notify(
        failed || partial
          ? `建模结束：${failed} 份失败，${partial} 份部分成功`
          : "全部材料建模完成，可进入流水校核",
      );
    }
    previousActiveMaterials.current = activeMaterialCount;
  }, [activeMaterialCount, materials]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setTick((x) => x + 1), 520);
    return () => clearInterval(timer);
  }, [playing]);
  useEffect(() => {
    if (!caseId || !selectedNode || !caseInfo?.victims[0]) {
      setAttributionData(null);
      return;
    }
    api
      .getAttribution(
        caseId,
        selectedNode,
        caseInfo.victims[0].reported_loss,
        50000,
      )
      .then(setAttributionData)
      .catch(() => setAttributionData(null));
  }, [caseId, selectedNode, caseInfo]);
  const relatedTransactions = useMemo(
    () =>
      selectedTx
        ? [selectedTx]
        : selectedEdge
          ? transactions.filter(
              (t) => `${t.payer_account}>${t.payee_account}` === selectedEdge,
            )
          : selectedNode
            ? transactions.filter(
                (t) =>
                  t.payer_account === selectedNode ||
                  t.payee_account === selectedNode,
              )
            : transactions,
    [transactions, selectedTx, selectedEdge, selectedNode],
  );
  const currentNode = graph.nodes.find((n) => n.id === selectedNode);
  const currentEdge = graph.edges.find((e) => e.id === selectedEdge);
  const selectNode = useCallback((id: string) => {
    setSelectedNode(id);
    setSelectedEdge(null);
    setSelectedTx(null);
  }, []);
  const selectEdge = useCallback((id: string) => {
    setSelectedEdge(id);
    setSelectedNode(null);
    setSelectedTx(null);
  }, []);
  const selectTransaction = useCallback((tx: Transaction | null) => {
    const selection = selectionForTransaction(tx);
    setSelectedTx(selection.selectedTx);
    setSelectedNode(selection.selectedNode);
    setSelectedEdge(selection.selectedEdge);
  }, []);
  const clearSelection = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedTx(null);
  }, []);
  const changeCase = (nextCaseId: string, confirmSwitch: boolean) => {
    if (!nextCaseId || nextCaseId === caseId) return;
    if (
      confirmSwitch &&
      caseId &&
      !window.confirm("切换案件后，当前页面将显示另一案件的数据。确认切换？")
    ) {
      return;
    }
    clearSelection();
    setCaseId(nextCaseId);
  };
  const handleUpload = async (files: FileList | null) => {
    if (!files || !caseId) return;
    setBusy(true);
    try {
      await api.uploadMaterials(caseId, [...files]);
      notify(`已接收 ${files.length} 份材料，正在自动建模`);
      await reload();
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="shell">
      <header className="topbar">
        <button className="icon bare" title="菜单">
          <Menu size={18} />
        </button>
        <div className="brand-mark">穿</div>
        <div className="brand">
          <strong>涉诈资金链路分析系统</strong>
          <span>多源流水归集 · 资金穿透研判</span>
        </div>
        <div className="case-switch">
          <span>当前案件</span>
          <select
            value={caseId}
            onChange={(e) => changeCase(e.target.value, tab !== "cases")}
          >
            {cases.map((c) => (
              <option key={c.case_id} value={c.case_id}>
                {c.case_number} · {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="top-status">
          <i />
          内网单机 · 文件存储
        </div>
        <div className="disclaimer">
          研判辅助系统
          <br />
          结果不构成司法认定
        </div>
      </header>
      <nav className="rail">
        {tabs.map(([id, label, Icon]) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
            title={label}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
        <div className="rail-bottom">
          <button title="系统说明">
            <CircleHelp size={18} />
          </button>
        </div>
      </nav>
      <section className={`content ${tab !== "cases" && caseInfo ? "with-workflow" : ""}`}>
        {tab !== "cases" && caseInfo && (
          <CaseWorkflowBar caseInfo={caseInfo} current={tab} onNavigate={setTab} />
        )}
        {tab === "cases" && (
          <CasesView
            cases={cases}
            current={caseId}
            caseInfo={caseInfo}
            materials={materials}
            transactions={allTransactions}
            versions={versions}
            seeds={seeds}
            onUpload={() => setTab("materials")}
            onOpen={(id) => {
              changeCase(id, false);
            }}
            onCreate={async (value) => {
              const created = await api.createCase(value);
              setCases((current) =>
                current.some((item) => item.case_id === created.case_id)
                  ? current
                  : [...current, created],
              );
              clearSelection();
              setCaseId(created.case_id);
              setTab("materials");
              notify("案件已建立，已进入材料接收");
            }}
          />
        )}
        {tab === "materials" && (
          <MaterialsView
            caseId={caseId}
            materials={materials}
            busy={busy}
            onUpload={handleUpload}
            onParse={async (id) => {
              setBusy(true);
              try {
                const result: any = await api.parseMaterial(caseId, id, true);
                notify(result.material.status === "failed" ? "材料建模失败，请查看错误" : `材料建模完成，生成 ${result.material.draft_count || 0} 笔草稿`);
                await reload();
                if (result.material.status !== "failed" && result.material.draft_count > 0) {
                  setTab("review");
                }
              } catch (e: any) {
                notify(e.message);
              } finally {
                setBusy(false);
              }
            }}
          />
        )}
        {tab === "review" && (
          <ReviewView
            caseId={caseId}
            transactions={transactions}
            materials={materials}
            total={total}
            status={status}
            setStatus={setStatus}
            onSelect={setSelectedTx}
            onConfirm={async (tx) => {
              await api.updateTransaction(caseId, tx.transaction_id, {
                review_status: "confirmed",
                review_note: "人工逐笔确认",
              });
              await reload();
            }}
            onConfirmAll={async () => {
              await api.confirmAll(caseId);
              notify("当前草稿已批量确认");
              await reload();
            }}
            onVersion={async () => {
              const v = await api.createVersion(
                caseId,
                `确认版 ${versions.length + 1}`,
              );
              notify(`已生成 ${v.version_id}`);
              await reload();
            }}
            versions={versions}
          />
        )}
        {tab === "seeds" && (
          <SeedsView
            caseInfo={caseInfo}
            transactions={allTransactions}
            seeds={seeds}
            onCreate={async (tx, victim) => {
              await api.createSeed(caseId, {
                transaction_id: tx.transaction_id,
                victim_id: victim,
                amount: tx.amount,
                confirmed_by: "办案人员",
              });
              notify("涉诈起点已确认");
              await reload();
            }}
            onCancel={async (seed) => {
              setSeeds((current) =>
                current.filter((item) => item.seed_id !== seed.seed_id),
              );
              try {
                await api.deleteSeed(caseId, seed.seed_id);
                notify("涉诈起点已取消");
              } catch (error: any) {
                setSeeds((current) =>
                  current.some((item) => item.seed_id === seed.seed_id)
                    ? current
                    : [...current, seed],
                );
                notify(error.message || "涉诈起点取消失败");
              }
            }}
          />
        )}
        {tab === "analysis" && (
          <AnalysisView
            caseInfo={caseInfo}
            graph={graph}
            filters={filters}
            setFilters={setFilters}
            selectedNode={selectedNode}
            selectedEdge={selectedEdge}
            selectedTx={selectedTx}
            selectNode={selectNode}
            selectEdge={selectEdge}
            setSelectedTx={selectTransaction}
            currentNode={currentNode}
            currentEdge={currentEdge}
            transactions={relatedTransactions}
            total={total}
            attribution={attribution}
            setAttribution={setAttribution}
            attributionData={attributionData}
            playing={playing}
            setPlaying={setPlaying}
            tick={tick}
            clear={clearSelection}
            caseId={caseId}
          />
        )}
      </section>
      {toast && (
        <div className="toast">
          <BadgeCheck size={16} />
          {toast}
        </div>
      )}
    </main>
  );
}

function CaseWorkflowBar({
  caseInfo,
  current,
  onNavigate,
}: {
  caseInfo: CaseRecord;
  current: string;
  onNavigate: (tab: string) => void;
}) {
  const steps = [
    ["materials", "材料接收"],
    ["review", "流水校核"],
    ["seeds", "确认起点"],
    ["analysis", "资金研判"],
  ] as const;
  return (
    <div className="case-workflow" aria-label="案件工作流程">
      <strong>{caseInfo.case_number} · {caseInfo.name}</strong>
      <div>
        {steps.map(([id, label], index) => (
          <button
            key={id}
            className={current === id ? "active" : ""}
            aria-label={`进入${label}`}
            onClick={() => onNavigate(id)}
          >
            <span>{index + 1}</span>{label}
          </button>
        ))}
      </div>
    </div>
  );
}

function CasesView({
  cases,
  current,
  caseInfo,
  materials,
  transactions,
  versions,
  seeds,
  onUpload,
  onOpen,
  onCreate,
}: {
  cases: CaseRecord[];
  current: string;
  caseInfo: CaseRecord | null;
  materials: Material[];
  transactions: Transaction[];
  versions: Version[];
  seeds: Seed[];
  onUpload: () => void;
  onOpen: (id: string) => void;
  onCreate: (v: unknown) => void;
}) {
  const [form, setForm] = useState({
    case_number: "",
    name: "",
    victim_name: "",
    victim_accounts: "",
    reported_loss: "",
  });
  const activeCase = caseInfo?.case_id === current
    ? caseInfo
    : cases.find((item) => item.case_id === current) || null;
  const pendingReview = transactions.filter(
    (transaction) => transaction.review_status !== "confirmed" && transaction.review_status !== "rejected",
  ).length;
  return (
    <div className="page scroll">
      <PageTitle
        kicker="CASE REGISTRY"
        title="案件中心"
        note="案件、受害人和材料以 case_id 独立隔离"
      />
      <form
        className="case-form"
        onSubmit={(e) => {
          e.preventDefault();
          onCreate({
            case_number: form.case_number,
            name: form.name,
            victims: form.victim_name
              ? [
                  {
                    name: form.victim_name,
                    accounts: form.victim_accounts
                      .split(/[,，;；\s]+/)
                      .map((account) => account.trim())
                      .filter(Boolean),
                    reported_loss: Number(form.reported_loss) || 0,
                  },
                ]
              : [],
          });
        }}
      >
        <b>新建案件</b>
        <input
          required
          placeholder="案件编号"
          value={form.case_number}
          onChange={(e) => setForm({ ...form, case_number: e.target.value })}
        />
        <input
          required
          placeholder="案件名称"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          placeholder="受害人姓名"
          value={form.victim_name}
          onChange={(e) => setForm({ ...form, victim_name: e.target.value })}
        />
        <input
          placeholder="受害人付款账号"
          value={form.victim_accounts}
          onChange={(e) => setForm({ ...form, victim_accounts: e.target.value })}
        />
        <input
          type="number"
          placeholder="报案损失"
          value={form.reported_loss}
          onChange={(e) => setForm({ ...form, reported_loss: e.target.value })}
        />
        <button className="primary">建立案件</button>
      </form>
      {activeCase && (
        <section className="case-overview" aria-label="当前案件概览">
          <div className="case-overview-title">
            <span>{activeCase.case_number}</span>
            <h2>{activeCase.name}</h2>
            <p>
              {activeCase.victims.map((victim) => victim.name).join("、") || "未登记受害人"}
              {" · "}研判状态：进行中
            </p>
          </div>
          <div className="case-overview-metrics">
            <div><span>案件材料</span><b>{materials.length}</b></div>
            <div><span>待校核流水</span><b>{pendingReview}</b></div>
            <div><span>确认版本</span><b>{versions.length}</b></div>
            <div><span>已确认起点</span><b>{seeds.length}</b></div>
          </div>
          <button className="primary" onClick={onUpload}>
            <Upload size={15} />上传本案材料
          </button>
        </section>
      )}
      <div className="case-list">
        {cases.map((c) => (
          <article
            className={c.case_id === current ? "case-row active" : "case-row"}
            key={c.case_id}
          >
            <div className="case-code">{c.case_number}</div>
            <div>
              <h3>{c.name}</h3>
              <p>
                {c.victims.length} 名受害人 · 报案损失{" "}
                {money(c.victims.reduce((s, v) => s + v.reported_loss, 0))}
              </p>
            </div>
            <span className="status ok">研判中</span>
            <button className="command" onClick={() => onOpen(c.case_id)}>
              进入案件 <ChevronRight size={14} />
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}
function MaterialsView({
  caseId,
  materials,
  busy,
  onUpload,
  onParse,
}: {
  caseId: string;
  materials: Material[];
  busy: boolean;
  onUpload: (f: FileList | null) => void;
  onParse: (id: string) => void;
}) {
  return (
    <div className="page scroll">
      <PageTitle
        kicker="EVIDENCE INTAKE"
        title="材料接收"
        note="原始材料按 SHA-256 只读归档；模型结果仅作为校核草稿"
      />
      <label className="dropzone">
        <Upload size={28} />
        <strong>{busy ? "正在处理材料…" : "拖入或选择案件材料"}</strong>
        <span>图片 / PDF / Word / CSV / Excel / ZIP / RAR / 文件夹</span>
        <input
          type="file"
          multiple
          onChange={(e) => onUpload(e.target.files)}
        />
      </label>
      <label className="folder-picker">
        <FolderOpen size={16} />
        选择文件夹
        <input
          type="file"
          multiple
          {...({ webkitdirectory: "", directory: "" } as any)}
          onChange={(e) => onUpload(e.target.files)}
        />
      </label>
      <div className="section-head">
        <h2>材料清单</h2>
        <span>{materials.length} 份</span>
      </div>
      <div className="material-list">
        {materials.map((m) => (
          <div className="material-row" key={m.file_id}>
            <FileArchive size={20} />
            <div>
              <b>{m.relative_path || m.original_name}</b>
              <small>
                SHA-256 {m.sha256.slice(0, 16)}… · {(m.size / 1024).toFixed(1)}{" "}
                KB
              </small>
              {m.errors?.[0] && (
                <small className="material-error">
                  {typeof m.errors[0] === "string" ? m.errors[0] : m.errors[0].error}
                </small>
              )}
            </div>
            <span className={`status ${m.status === "parsed" ? "ok" : ""} ${["queued", "parsing"].includes(m.status) ? "working" : ""}`}>
              {["queued", "parsing"].includes(m.status) && <LoaderCircle size={12} />}
              {m.status === "failed"
                ? "建模失败"
                : m.status === "partial"
                  ? "部分成功"
                  : m.status === "queued"
                    ? "排队中"
                    : m.status === "parsing"
                      ? "建模中"
                  : m.duplicate
                ? "重复材料"
                : m.status === "parsed"
                  ? "已完成"
                  : "待处理"}
            </span>
            <a
              className="command"
              href={`/api/cases/${caseId}/materials/${m.file_id}/download`}
              target="_blank"
            >
              原始证据
            </a>
            {["failed", "partial", "uploaded"].includes(m.status) && (
              <button className="command" onClick={() => onParse(m.file_id)}>
                <FileSearch size={14} /> 重新建模
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
function ReviewView({
  caseId,
  transactions,
  materials,
  total,
  status,
  setStatus,
  onSelect,
  onConfirm,
  onConfirmAll,
  onVersion,
  versions,
}: {
  caseId: string;
  transactions: Transaction[];
  materials: Material[];
  total: number;
  status: string;
  setStatus: (s: string) => void;
  onSelect: (t: Transaction) => void;
  onConfirm: (t: Transaction) => void;
  onConfirmAll: () => void;
  onVersion: () => void;
  versions: Version[];
}) {
  return (
    <div className="page review-page">
      <PageTitle
        kicker="HUMAN REVIEW GATE"
        title="流水校核"
        note="未经人工确认的记录不能进入正式穿透分析"
      />
      <div className="toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          <option value="pending">待确认</option>
          <option value="confirmed">已确认</option>
          <option value="conflict">冲突</option>
        </select>
        <span>{total} 笔草稿</span>
        <button className="secondary" onClick={onConfirmAll}>
          <BadgeCheck size={14} />
          批量人工确认
        </button>
        <button className="primary" onClick={onVersion}>
          <FileCheck2 size={14} />
          生成确认版 CSV
        </button>
      </div>
      <TransactionTable
        rows={transactions}
        selected={null}
        onSelect={onSelect}
        review
        onConfirm={onConfirm}
        materials={materials}
      />
      <div className="version-strip">
        <b>确认版本</b>
        {versions.map((v) => (
          <a
            key={v.version_id}
            href={`/api/cases/${caseId}/versions/${v.version_id}/download`}
          >
            {v.version_id} · {v.record_count}笔 · {v.sha256.slice(0, 8)}
          </a>
        ))}
      </div>
    </div>
  );
}
function SeedsView({
  caseInfo,
  transactions,
  seeds,
  onCreate,
  onCancel,
}: {
  caseInfo: CaseRecord | null;
  transactions: Transaction[];
  seeds: Seed[];
  onCreate: (t: Transaction, v: string) => void;
  onCancel: (seed: Seed) => void;
}) {
  const [nameQuery, setNameQuery] = useState("");
  const victims = caseInfo?.victims || [];
  const victimAccounts = new Map(
    victims.flatMap((item) =>
      item.accounts.map((account) => [
        account.replace(/[^a-zA-Z0-9]/g, ""),
        item,
      ] as const),
    ),
  );
  const candidates = transactions.filter(
    (transaction) =>
      transaction.review_status === "confirmed" &&
      victimAccounts.has(transaction.payer_account.replace(/[^a-zA-Z0-9]/g, "")),
  );
  const visibleCandidates = candidates.filter((transaction) => {
    const query = nameQuery.trim().toLowerCase();
    return (
      !query ||
      transaction.payer_name.toLowerCase().includes(query) ||
      transaction.payee_name.toLowerCase().includes(query)
    );
  });
  return (
    <div className="page scroll">
      <PageTitle
        kicker="CONFIRMED ORIGIN"
        title="涉诈起点"
        note="起点必须由办案人员人工确认，金额作为归因上限"
      />
      <div className="seed-summary">
        <div>
          <span>受害人数</span>
          <b>{caseInfo?.victims.length || 0}</b>
        </div>
        <div>
          <span>已确认起点</span>
          <b>{seeds.length}</b>
        </div>
        <div>
          <span>起点总额</span>
          <b>{money(seeds.reduce((s, x) => s + x.amount, 0))}</b>
        </div>
      </div>
      <div className="section-head">
        <h2>候选转账</h2>
        <span>从已确认流水选择</span>
      </div>
      <div className="seed-search">
        <label htmlFor="seed-name-query">姓名模糊查询</label>
        <input
          id="seed-name-query"
          placeholder="输入付款人或收款人姓名"
          value={nameQuery}
          onChange={(event) => setNameQuery(event.target.value)}
        />
      </div>
      <div className="seed-list">
        {visibleCandidates.slice(0, 24).map((t) => {
          const seed = seeds.find((item) => item.transaction_id === t.transaction_id);
          const payingVictim = victimAccounts.get(
            t.payer_account.replace(/[^a-zA-Z0-9]/g, ""),
          );
          return (
          <div className="seed-row" key={t.transaction_id}>
            <div>
              <b>
                {t.payer_name} → {t.payee_name}
              </b>
              <small>
                {t.transaction_time.replace("T", " ").slice(0, 19)} ·{" "}
                {t.serial_number}
              </small>
            </div>
            <strong>{money(t.amount)}</strong>
            <button
              className="command"
              disabled={!payingVictim}
              onClick={() =>
                seed
                  ? onCancel(seed)
                  : payingVictim && onCreate(t, payingVictim.victim_id)
              }
            >
              {seed ? "已确认（点击取消）" : "设为起点"}
            </button>
          </div>
          );
        })}
        {!visibleCandidates.length && (
          <div className="empty-state">暂无符合条件的已确认受害人付款流水</div>
        )}
      </div>
    </div>
  );
}

type AnalysisProps = {
  caseInfo: CaseRecord | null;
  graph: GraphData;
  filters: api.Filters;
  setFilters: React.Dispatch<React.SetStateAction<api.Filters>>;
  selectedNode: string | null;
  selectedEdge: string | null;
  selectedTx: Transaction | null;
  selectNode: (id: string) => void;
  selectEdge: (id: string) => void;
  setSelectedTx: (t: Transaction | null) => void;
  currentNode: any;
  currentEdge: any;
  transactions: Transaction[];
  total: number;
  attribution: string;
  setAttribution: (s: string) => void;
  attributionData: any;
  playing: boolean;
  setPlaying: (b: boolean) => void;
  tick: number;
  clear: () => void;
  caseId: string;
};
function AnalysisView(p: AnalysisProps) {
  const update = (key: keyof api.Filters, value: string | number) =>
    p.setFilters((current) => ({ ...current, [key]: value }));
  const [graphHeight, setGraphHeight] = useState(420);
  const analysisLayout = useRef<HTMLDivElement>(null);
  const resizeStart = useRef<{
    y: number;
    height: number;
    maximum: number;
  } | null>(null);
  const attributionResult = p.attributionData?.[p.attribution];
  const [traceEnd, setTraceEnd] = useState("");
  const [traceHops, setTraceHops] = useState(3);
  const [traceResult, setTraceResult] = useState<any>(null);
  const networkRisk = p.graph.risk_summary || EMPTY_GRAPH.risk_summary;
  const riskLead = p.graph.nodes.find((node) => node.id === networkRisk.account_id);
  useEffect(() => setTraceResult(null), [p.selectedNode]);
  return (
    <div
      ref={analysisLayout}
      className="analysis-layout"
      style={{ "--graph-height": `${graphHeight}px` } as React.CSSProperties}
    >
      <aside className="filters">
        <div className="panel-block">
          <span className="eyebrow">RISK ASSESSMENT</span>
          <div className="score">
            <b>{networkRisk.score}</b>
            <span>{networkRisk.level}</span>
          </div>
          <div className="meter">
            <i style={{ width: `${networkRisk.score}%` }} />
          </div>
          <div className="risk-basis">
            <b>{networkRisk.account_label}</b>
            <span>当前网络最高节点 · 内部规则 V1</span>
            {riskLead?.risk_factors.slice(0, 3).map((factor) => (
              <small key={factor.code}>
                {factor.name} +{factor.score}
              </small>
            ))}
            <em>{networkRisk.disclaimer}</em>
          </div>
          <Metric label="关联账户" value={`${p.graph.nodes.length}`} />
          <Metric label="聚合路径" value={`${p.graph.edges.length}`} />
          <Metric label="穿透金额" value={money(p.graph.total_amount)} />
          <Metric label="原始流水" value={`${p.graph.transaction_count} 笔`} />
        </div>
        <div className="panel-block">
          <span className="eyebrow">SEARCH & FILTER</span>
          <label>
            全文查询
            <div className="search">
              <Search size={14} />
              <input
                value={p.filters.query}
                onChange={(e) => update("query", e.target.value)}
                placeholder="卡号 / 户名 / 流水号 / 摘要"
              />
            </div>
          </label>
          <label>
            最低单笔金额 <b>{money(p.filters.minAmount)}</b>
            <input
              type="range"
              min="0"
              max="100000"
              step="5000"
              value={p.filters.minAmount}
              onChange={(e) => update("minAmount", +e.target.value)}
            />
          </label>
          <div className="date-pair">
            <label>
              开始日期
              <input
                type="date"
                value={p.filters.dateFrom}
                onChange={(e) => update("dateFrom", e.target.value)}
              />
            </label>
            <label>
              结束日期
              <input
                type="date"
                value={p.filters.dateTo}
                onChange={(e) => update("dateTo", e.target.value)}
              />
            </label>
          </div>
          <label>
            资金方向
            <select
              value={p.filters.direction}
              onChange={(e) => update("direction", e.target.value)}
            >
              <option value="all">全部方向</option>
              <option value="forward">下游流出</option>
              <option value="return">资金回流</option>
            </select>
          </label>
          <label>
            交易渠道
            <select
              value={p.filters.channel}
              onChange={(e) => update("channel", e.target.value)}
            >
              <option value="">全部渠道</option>
              <option>手机银行</option>
              <option>网上银行</option>
              <option>超级网银</option>
              <option>ATM转账</option>
              <option>快捷支付</option>
            </select>
          </label>
          <label>
            银行机构
            <div className="search">
              <Search size={14} />
              <input
                value={p.filters.bank}
                onChange={(e) => update("bank", e.target.value)}
                placeholder="银行或开户机构"
              />
            </div>
          </label>
          <label>
            地区
            <select
              value={p.filters.region}
              onChange={(e) => update("region", e.target.value)}
            >
              <option value="">全部地区</option>
              <option>湖南长沙</option>
              <option>广东深圳</option>
              <option>福建厦门</option>
              <option>湖北武汉</option>
              <option>广西南宁</option>
            </select>
          </label>
          <label>
            流水排序
            <select
              value={p.filters.sort}
              onChange={(e) => update("sort", e.target.value)}
            >
              <option value="time_asc">时间由早到晚</option>
              <option value="time_desc">时间由近到远</option>
              <option value="amount_desc">金额由高到低</option>
            </select>
          </label>
          <label>
            归因口径
            <select
              value={p.attribution}
              onChange={(e) => p.setAttribution(e.target.value)}
            >
              <option value="fifo">时间优先 FIFO</option>
              <option value="conservative">保守下限</option>
              <option value="possible_max">可能上限</option>
              <option value="proportional">比例分摊</option>
            </select>
          </label>
          <div className="attribution-note">
            <ShieldAlert size={15} />
            <span>
              当前结果为<b>推定资金路径</b>
              {attributionResult && (
                <>
                  ，归因 {money(attributionResult.total_attributed)}，剩余{" "}
                  {money(attributionResult.remaining_amount)}
                </>
              )}
              。
            </span>
          </div>
        </div>
      </aside>
      <section className="graph-workspace">
        <div className="graph-toolbar">
          <div>
            <b>资金拓扑</b>
            <span>二维平铺 · 自由平移缩放 · 点击查看直接入度和出度</span>
          </div>
          <div>
            <button
              className={p.playing ? "tool active" : "tool"}
              onClick={() => p.setPlaying(!p.playing)}
            >
              {p.playing ? <Pause size={15} /> : <Play size={15} />}{" "}
              {p.playing ? "停止" : "播放"}
            </button>
            <button className="tool" onClick={p.clear}>
              <RefreshCcw size={15} />
              复位选择
            </button>
          </div>
        </div>
        <GraphCanvas
          data={p.graph}
          selectedNode={p.selectedNode}
          selectedEdge={p.selectedEdge}
          onNode={p.selectNode}
          onEdge={p.selectEdge}
          playing={p.playing}
          playTick={p.tick}
        />
        <div className="graph-legend">
          <span>
            <i className="red" />
            高风险核心
          </span>
          <span>
            <i className="amber" />
            关联账户
          </span>
          <span>
            <i className="cyan" />
            资金路径
          </span>
        </div>
      </section>
      <aside className="inspector">
        <div className="panel-block">
          <span className="eyebrow">TRACE INSPECTOR</span>
          {p.currentNode ? (
            <>
              <div className="identity">
                <div>{p.currentNode.label.slice(0, 1)}</div>
                <section>
                  <h2>{p.currentNode.label}</h2>
                  <p>{mask(p.currentNode.account)}</p>
                </section>
              </div>
              <div className="tags">
                <span>风险 {p.currentNode.risk}</span>
                <span>{p.currentNode.risk_level}</span>
              </div>
              <div className="risk-rules">
                <b>内部规则命中</b>
                {p.currentNode.risk_factors.length ? (
                  p.currentNode.risk_factors.map((factor: any) => (
                    <div key={factor.code}>
                      <span>{factor.name}</span>
                      <strong>+{factor.score}</strong>
                      <small>{factor.evidence}</small>
                    </div>
                  ))
                ) : (
                  <p>当前筛选范围未命中内部风险规则。</p>
                )}
              </div>
              <Metric label="累计流入" value={money(p.currentNode.incoming)} />
              <Metric label="累计流出" value={money(p.currentNode.outgoing)} />
              <Metric
                label="当前口径归因"
                value={
                  attributionResult
                    ? money(attributionResult.total_attributed)
                    : "选择账户后计算"
                }
              />
              <Metric label="开户机构" value={p.currentNode.bank || "待核验"} />
              <div className="trace-query">
                <b>路径追踪</b>
                <input value={traceEnd} onChange={(e)=>setTraceEnd(e.target.value)} placeholder="目标账户，可留空"/>
                <select value={traceHops} onChange={(e)=>setTraceHops(+e.target.value)}>{[1,2,3,4,5,6,7,8].map(h=><option key={h} value={h}>{h} 跳</option>)}</select>
                <button className="command" onClick={async()=>setTraceResult(await api.traceNetwork(p.caseId,p.selectedNode!,traceEnd,traceHops))}>查询路径</button>
                {traceResult&&<div className="trace-result"><span>上游 {traceResult.upstream.length} · 下游 {traceResult.downstream.length}</span><span>最短路径 {traceResult.shortest_path.length?traceResult.shortest_path.join(' → '):'未指定或未发现'}</span><span>回流环路 {traceResult.cycles.length} 条</span></div>}
              </div>
            </>
          ) : p.selectedTx ? (
            <TransactionEvidence tx={p.selectedTx} />
          ) : p.currentEdge ? (
            <>
              <div className="identity">
                <div>↗</div>
                <section>
                  <h2>聚合资金路径</h2>
                  <p>{p.currentEdge.id}</p>
                </section>
              </div>
              <Metric label="路径金额" value={money(p.currentEdge.amount)} />
              <Metric label="原始笔数" value={`${p.currentEdge.count} 笔`} />
              <Metric label="证据状态" value="已确认流水" />
            </>
          ) : (
            <div className="empty-inspector">
              <Gauge size={28} />
              <p>选择账户、路径或原始流水，查看资金、风险与证据来源。</p>
            </div>
          )}
        </div>
      </aside>
      <button
        className="analysis-splitter"
        aria-label="调整拓扑图和转账数据高度"
        onPointerDown={(event) => {
          resizeStart.current = {
            y: event.clientY,
            height: graphHeight,
            maximum: maximumGraphHeight(
              analysisLayout.current?.clientHeight || 0,
              180,
            ),
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!resizeStart.current) return;
          setGraphHeight(
            resizeAnalysisSplit(
              resizeStart.current.height,
              event.clientY - resizeStart.current.y,
              180,
              resizeStart.current.maximum,
            ),
          );
        }}
        onPointerUp={() => {
          resizeStart.current = null;
        }}
        onPointerCancel={() => {
          resizeStart.current = null;
        }}
        onLostPointerCapture={() => {
          resizeStart.current = null;
        }}
      />
      <section className="raw-data">
        <div className="raw-head">
          <b>原始转账数据</b>
          <span>
            {p.transactions.length} / {p.total}
          </span>
          <p>
            {p.selectedNode
              ? "已定位账户直接关联流水"
              : p.selectedEdge
                ? "已定位路径全部原始流水"
                : "当前筛选范围完整银行流水"}
          </p>
          <a
            className="export"
            href={`/api/cases/${p.caseId}/exports/transactions`}
          >
            <Download size={14} />
            导出 CSV
          </a>
        </div>
        <TransactionTable
          rows={p.transactions}
          selected={p.selectedTx?.transaction_id || null}
          onSelect={p.setSelectedTx}
        />
      </section>
    </div>
  );
}
function TransactionEvidence({ tx }: { tx: Transaction }) {
  return (
    <div className="evidence">
      <div className="identity">
        <div>单</div>
        <section>
          <h2>原始流水</h2>
          <p>{tx.serial_number}</p>
        </section>
      </div>
      <Metric label="付款方" value={tx.payer_name} />
      <Metric label="收款方" value={tx.payee_name} />
      <Metric label="交易金额" value={money(tx.amount)} />
      <Metric
        label="证据类型"
        value={tx.provenance === "human_confirmed" ? "人工确认" : "模型建议"}
      />
      <Metric
        label="来源定位"
        value={
          tx.source.source_file_id
            ? `${tx.source.source_file_id.slice(0, 8)} · 第${tx.source.page_number || "-"}页`
            : "演示数据"
        }
      />
    </div>
  );
}
function TransactionTable({
  rows,
  selected,
  onSelect,
  review = false,
  onConfirm,
  materials = [],
}: {
  rows: Transaction[];
  selected: string | null;
  onSelect: (t: Transaction) => void;
  review?: boolean;
  onConfirm?: (t: Transaction) => void;
  materials?: Material[];
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>交易时间</th>
            <th>交易流水号</th>
            <th>付款账号</th>
            <th>付款户名</th>
            <th>付款开户行</th>
            <th>收款账号</th>
            <th>收款户名</th>
            <th>收款开户行</th>
            <th>借贷</th>
            <th>交易金额</th>
            <th>交易后余额</th>
            <th>渠道</th>
            <th>摘要</th>
            <th>地区</th>
            {review && <th>数据来源</th>}
            {review && <th>校核</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((tx) => (
            <tr
              key={tx.transaction_id}
              className={selected === tx.transaction_id ? "selected" : ""}
              onClick={() => onSelect(tx)}
            >
              <td>{tx.transaction_time.replace("T", " ").slice(0, 19)}</td>
              <td>{tx.serial_number}</td>
              <td>{mask(tx.payer_account)}</td>
              <td>{tx.payer_name}</td>
              <td>{tx.payer_bank}</td>
              <td>{mask(tx.payee_account)}</td>
              <td>{tx.payee_name}</td>
              <td>{tx.payee_bank}</td>
              <td className="debit">{tx.debit_credit}</td>
              <td className="amount">{money(tx.amount)}</td>
              <td>
                {tx.balance_after == null ? "-" : money(tx.balance_after)}
              </td>
              <td>{tx.channel}</td>
              <td>{tx.summary}</td>
              <td>{tx.region}</td>
              {review && (
                <td
                  className="source-cell"
                  title={transactionSourceLabel(tx, materials)}
                >
                  {transactionSourceLabel(tx, materials)}
                </td>
              )}
              {review && (
                <td>
                  <button
                    className={`mini ${tx.review_status === "confirmed" ? "done" : ""}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onConfirm?.(tx);
                    }}
                  >
                    {tx.review_status === "confirmed" ? "已确认" : "确认"}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function PageTitle({
  kicker,
  title,
  note,
}: {
  kicker: string;
  title: string;
  note: string;
}) {
  return (
    <header className="page-title">
      <span>{kicker}</span>
      <h1>{title}</h1>
      <p>{note}</p>
    </header>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
