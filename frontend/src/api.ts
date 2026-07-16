import type {
  CaseRecord,
  GraphData,
  Material,
  Seed,
  Transaction,
  Version,
} from "./types";
const json = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(url, init);
  if (!r.ok)
    throw new Error(
      (await r.json().catch(() => ({ detail: r.statusText }))).detail ||
        r.statusText,
    );
  return r.json();
};
const body = (value: unknown) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(value),
});
export const bootstrapDemo = () =>
  json<{ case_id: string }>("/api/demo/bootstrap", { method: "POST" });
export const listCases = () => json<CaseRecord[]>("/api/cases");
export const createCase = (value: unknown) =>
  json<CaseRecord>("/api/cases", body(value));
export const getCase = (id: string) => json<CaseRecord>(`/api/cases/${id}`);
export const listMaterials = (id: string) =>
  json<Material[]>(`/api/cases/${id}/materials`);
export const uploadMaterials = (id: string, files: File[]) => {
  const data = new FormData();
  files.forEach((f) => {
    data.append("files", f);
    data.append("relative_paths", f.webkitRelativePath || f.name);
  });
  return json<Material[]>(`/api/cases/${id}/materials`, {
    method: "POST",
    body: data,
  });
};
export const parseMaterial = (
  caseId: string,
  fileId: string,
  useModel = false,
) =>
  json(`/api/cases/${caseId}/materials/${fileId}/parse?use_model=${useModel}`, {
    method: "POST",
  });
export type Filters = {
  query: string;
  status?: string;
  minAmount: number;
  direction: string;
  channel: string;
  bank: string;
  region: string;
  dateFrom: string;
  dateTo: string;
  sort: string;
};
const params = (f: Filters) =>
  new URLSearchParams({
    query: f.query,
    status: f.status || "",
    min_amount: String(f.minAmount),
    direction: f.direction,
    channel: f.channel,
    bank: f.bank,
    region: f.region,
    date_from: f.dateFrom,
    date_to: f.dateTo,
    sort: f.sort,
  }).toString();
export const getTransactions = (id: string, filters: Filters) =>
  json<{ items: Transaction[]; total: number }>(
    `/api/cases/${id}/draft-transactions?page_size=500&${params(filters)}`,
  );
export const updateTransaction = (
  caseId: string,
  txId: string,
  value: unknown,
) =>
  json<Transaction>(`/api/cases/${caseId}/draft-transactions/${txId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  });
export const confirmAll = (id: string) =>
  json(`/api/cases/${id}/draft-transactions/confirm-all`, { method: "POST" });
export const listVersions = (id: string) =>
  json<Version[]>(`/api/cases/${id}/versions`);
export const createVersion = (id: string, name: string) =>
  json<Version>(`/api/cases/${id}/versions`, body({ name }));
export const listSeeds = (id: string) => json<Seed[]>(`/api/cases/${id}/seeds`);
export const createSeed = (id: string, value: unknown) =>
  json<Seed>(`/api/cases/${id}/seeds`, body(value));
export const getGraph = (id: string, filters: Filters) =>
  json<GraphData>(`/api/cases/${id}/analysis/graph?${params(filters)}`);
export const getAttribution = (
  id: string,
  source: string,
  victimAmount: number,
  preexistingBalance: number,
) =>
  json<
    Record<
      string,
      {
        total_attributed: number;
        remaining_amount: number;
        edges: { transaction_id: string; attributed_amount: number }[];
        disclaimer: string;
      }
    >
  >(
    `/api/cases/${id}/analysis/attribute?source_account=${encodeURIComponent(source)}&victim_amount=${victimAmount}&preexisting_balance=${preexistingBalance}`,
    { method: "POST" },
  );
export const traceNetwork = (
  id: string,
  start: string,
  end: string,
  hops: number,
) =>
  json<{
    upstream: string[];
    downstream: string[];
    shortest_path: string[];
    cycles: string[][];
  }>(
    `/api/cases/${id}/analysis/trace?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&hops=${hops}`,
  );
export const getEvidence = (id: string, txId: string) =>
  json(`/api/cases/${id}/evidence/${txId}`);
