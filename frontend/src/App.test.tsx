import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import * as api from './api'
import App from './App'

vi.mock('./api', () => ({
  bootstrapDemo: vi.fn().mockResolvedValue({ case_id: 'CASE-DEMO' }),
  listCases: vi.fn().mockResolvedValue([{ case_id: 'CASE-1', case_number: 'A-001', name: '测试案件', status: 'active', created_at: '2026-07-21', victims: [{ victim_id: 'V-1', name: '张某', accounts: ['62170001'], reported_loss: 100000 }] }]),
  getCase: vi.fn().mockResolvedValue({ case_id: 'CASE-1', case_number: 'A-001', name: '测试案件', status: 'active', created_at: '2026-07-21', victims: [{ victim_id: 'V-1', name: '张某', accounts: ['62170001'], reported_loss: 100000 }] }),
  getGraph: vi.fn().mockResolvedValue({ nodes: [], edges: [], transaction_count: 0, total_amount: 0, risk_summary: { score: 0, level: '低风险', account_id: null, account_label: '无', method: 'internal_rules_v1', disclaimer: '内部规则风险提示，不构成犯罪事实或司法认定。' } }),
  getTransactions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  listMaterials: vi.fn().mockResolvedValue([{ file_id: 'FILE-1', original_name: 'flow.csv', size: 10, sha256: 'abc', duplicate: false, status: 'uploaded' }]),
  listVersions: vi.fn().mockResolvedValue([]),
  listSeeds: vi.fn().mockResolvedValue([]),
  createCase: vi.fn().mockResolvedValue({ case_id: 'CASE-2' }),
  createSeed: vi.fn().mockResolvedValue({ seed_id: 'SEED-1' }),
  deleteSeed: vi.fn().mockResolvedValue({}),
  parseMaterial: vi.fn().mockResolvedValue({ material: { status: 'parsed', draft_count: 1 } }),
}))
vi.mock('./GraphCanvas', () => ({ default: () => <div data-testid="graph-canvas" /> }))

beforeEach(() => {
  vi.clearAllMocks()
})
afterEach(cleanup)

test('renders every investigation workspace and raw transaction baseline', () => {
  render(<App />)
  expect(screen.getByText('涉诈资金链路分析系统')).toBeInTheDocument()
  expect(screen.getByText('多源流水归集 · 资金穿透研判')).toBeInTheDocument()
  expect(screen.queryByText('FundTrace')).not.toBeInTheDocument()
  expect(screen.getByText('案件中心')).toBeInTheDocument()
  expect(screen.getByText('材料接收')).toBeInTheDocument()
  expect(screen.getByText('流水校核')).toBeInTheDocument()
  expect(screen.getByText('涉诈起点')).toBeInTheDocument()
  expect(screen.getByText('资金研判')).toBeInTheDocument()
  expect(screen.getByText('原始转账数据')).toBeInTheDocument()
  expect(screen.queryByText('92')).not.toBeInTheDocument()
  expect(screen.getByText('内部规则风险提示，不构成犯罪事实或司法认定。')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '案件中心' }))
  expect(screen.getByText('新建案件')).toBeInTheDocument()
})

test('analysis exposes a separator for resizing the graph and transaction table', () => {
  render(<App />)
  expect(
    screen.getByRole('button', { name: '调整拓扑图和转账数据高度' }),
  ).toBeInTheDocument()
})

test('material action explicitly extracts and models transactions', async () => {
  render(<App />)
  fireEvent.click(screen.getAllByRole('button', { name: '材料接收' }).at(-1)!)
  expect(await screen.findByRole('button', { name: /提取并建模/ })).toBeInTheDocument()
})

test('case creation captures the victim payment account', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '案件中心' }))
  fireEvent.change(screen.getByPlaceholderText('案件编号'), { target: { value: 'A-002' } })
  fireEvent.change(screen.getByPlaceholderText('案件名称'), { target: { value: '新案件' } })
  fireEvent.change(screen.getByPlaceholderText('受害人姓名'), { target: { value: '李某' } })
  fireEvent.change(screen.getByPlaceholderText('受害人付款账号'), { target: { value: '62220001' } })
  fireEvent.click(screen.getByRole('button', { name: '建立案件' }))

  await waitFor(() => expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({
    victims: [expect.objectContaining({ accounts: ['62220001'] })],
  })))
})

test('case center shows current-case overview and upload action', async () => {
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [
      { transaction_id: 'T-1', transaction_time: '2026-07-21T10:00:00', serial_number: 'S-1', payer_account: '62170001', payer_name: '张某', payer_bank: '', payee_account: '62220001', payee_name: '收款人', payee_bank: '', debit_credit: '借', amount: 1000, balance_after: null, channel: '', summary: '', region: '', review_status: 'pending', review_note: '', provenance: 'model_suggested', source: {} },
      { transaction_id: 'T-2', transaction_time: '2026-07-21T11:00:00', serial_number: 'S-2', payer_account: '62220001', payer_name: '收款人', payer_bank: '', payee_account: '62330001', payee_name: '下游', payee_bank: '', debit_credit: '借', amount: 800, balance_after: null, channel: '', summary: '', region: '', review_status: 'confirmed', review_note: '', provenance: 'human_confirmed', source: {} },
    ] as any,
    total: 2,
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '案件中心' }))

  expect(await screen.findByRole('heading', { level: 2, name: '测试案件' })).toBeInTheDocument()
  expect(screen.getByText('待校核流水')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /上传本案材料/ })).toBeInTheDocument()
})

test('case workspace keeps current case identity visible', async () => {
  render(<App />)
  expect(await screen.findByText('A-001 · 测试案件')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '进入流水校核' })).toBeInTheDocument()
})

test('successful material modeling enters transaction review', async () => {
  render(<App />)
  fireEvent.click(screen.getAllByRole('button', { name: '材料接收' }).at(-1)!)
  fireEvent.click(await screen.findByRole('button', { name: /提取并建模/ }))

  expect(await screen.findByRole('heading', { name: '流水校核' })).toBeInTheDocument()
})

test('seed candidates only include confirmed payments from the victim account', async () => {
  const transaction = (id: string, payerAccount: string, payeeName: string, reviewStatus: string) => ({
    transaction_id: id, transaction_time: '2026-07-21T10:00:00', serial_number: id,
    payer_account: payerAccount, payer_name: '付款人', payer_bank: '', payee_account: `${id}-PAYEE`,
    payee_name: payeeName, payee_bank: '', debit_credit: '借', amount: 1000, balance_after: null,
    channel: '', summary: '', region: '', review_status: reviewStatus, review_note: '',
    provenance: 'model_suggested', source: {},
  })
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [
      transaction('MATCH', '62170001', '有效收款人', 'confirmed'),
      transaction('PENDING', '62170001', '待确认收款人', 'pending'),
      transaction('OTHER', '62179999', '他人付款收款人', 'confirmed'),
    ] as any,
    total: 3,
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '涉诈起点' }))

  expect(await screen.findByText((_, element) => element?.textContent === '付款人 → 有效收款人')).toBeInTheDocument()
  expect(screen.queryByText('待确认收款人')).not.toBeInTheDocument()
  expect(screen.queryByText('他人付款收款人')).not.toBeInTheDocument()
})

test('clicking a confirmed seed again cancels it', async () => {
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [{
      transaction_id: 'MATCH', transaction_time: '2026-07-21T10:00:00', serial_number: 'MATCH',
      payer_account: '62170001', payer_name: '付款人', payer_bank: '', payee_account: '62220001',
      payee_name: '收款人', payee_bank: '', debit_credit: '借', amount: 1000, balance_after: null,
      channel: '', summary: '', region: '', review_status: 'confirmed', review_note: '',
      provenance: 'human_confirmed', source: {},
    }] as any,
    total: 1,
  })
  vi.mocked(api.listSeeds).mockResolvedValue([{
    seed_id: 'SEED-1', victim_id: 'V-1', transaction_id: 'MATCH', amount: 1000,
    confirmed_by: '办案人员', confirmed_at: '2026-07-21T10:00:00',
  }])
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '涉诈起点' }))
  fireEvent.click(await screen.findByRole('button', { name: /已确认.*点击取消/ }))

  await waitFor(() => expect(api.deleteSeed).toHaveBeenCalledWith('CASE-1', 'SEED-1'))
})

test('seed cancellation failure is visible to the user', async () => {
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [{
      transaction_id: 'MATCH', transaction_time: '2026-07-21T10:00:00', serial_number: 'MATCH',
      payer_account: '62170001', payer_name: '付款人', payer_bank: '', payee_account: '62220001',
      payee_name: '收款人', payee_bank: '', debit_credit: '借', amount: 1000, balance_after: null,
      channel: '', summary: '', region: '', review_status: 'confirmed', review_note: '',
      provenance: 'human_confirmed', source: {},
    }] as any,
    total: 1,
  })
  vi.mocked(api.listSeeds).mockResolvedValue([{
    seed_id: 'SEED-1', victim_id: 'V-1', transaction_id: 'MATCH', amount: 1000,
    confirmed_by: '办案人员', confirmed_at: '2026-07-21T10:00:00',
  }])
  vi.mocked(api.deleteSeed).mockRejectedValue(new Error('取消接口不可用'))
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '涉诈起点' }))
  fireEvent.click(await screen.findByRole('button', { name: /已确认.*点击取消/ }))

  expect(await screen.findByText('取消接口不可用')).toBeInTheDocument()
})

test('seed cancellation updates the list before the server responds', async () => {
  let resolveDelete: (() => void) | undefined
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [{
      transaction_id: 'MATCH', transaction_time: '2026-07-21T10:00:00', serial_number: 'MATCH',
      payer_account: '62170001', payer_name: '付款人', payer_bank: '', payee_account: '62220001',
      payee_name: '收款人', payee_bank: '', debit_credit: '借', amount: 1000, balance_after: null,
      channel: '', summary: '', region: '', review_status: 'confirmed', review_note: '',
      provenance: 'human_confirmed', source: {},
    }] as any,
    total: 1,
  })
  vi.mocked(api.listSeeds).mockResolvedValue([{
    seed_id: 'SEED-1', victim_id: 'V-1', transaction_id: 'MATCH', amount: 1000,
    confirmed_by: '办案人员', confirmed_at: '2026-07-21T10:00:00',
  }])
  vi.mocked(api.deleteSeed).mockReturnValue(new Promise((resolve) => {
    resolveDelete = () => resolve({ seed_id: 'SEED-1', status: 'cancelled' })
  }))
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '涉诈起点' }))
  fireEvent.click(await screen.findByRole('button', { name: /已确认.*点击取消/ }))

  expect(await screen.findByRole('button', { name: '设为起点' })).toBeInTheDocument()
  resolveDelete?.()
})

test('seed candidates can be filtered by payer or payee name', async () => {
  const transaction = (id: string, payerName: string, payeeName: string) => ({
    transaction_id: id, transaction_time: '2026-07-21T10:00:00', serial_number: id,
    payer_account: '62170001', payer_name: payerName, payer_bank: '', payee_account: `${id}-PAYEE`,
    payee_name: payeeName, payee_bank: '', debit_credit: '借', amount: 1000, balance_after: null,
    channel: '', summary: '', region: '', review_status: 'confirmed', review_note: '',
    provenance: 'human_confirmed', source: {},
  })
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [
      transaction('T-1', '张某', '李某'),
      transaction('T-2', '张某', '王某'),
    ] as any,
    total: 2,
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '涉诈起点' }))
  fireEvent.change(await screen.findByLabelText('姓名模糊查询'), {
    target: { value: '李' },
  })

  expect(screen.getByText((_, element) => element?.textContent === '张某 → 李某')).toBeInTheDocument()
  expect(screen.queryByText((_, element) => element?.textContent === '张某 → 王某')).not.toBeInTheDocument()
})

test('review table shows the source material and evidence location', async () => {
  vi.mocked(api.getTransactions).mockResolvedValue({
    items: [{
      transaction_id: 'SOURCE-TX', transaction_time: '2026-07-21T10:00:00', serial_number: 'SOURCE-1',
      payer_account: '62170001', payer_name: '张某', payer_bank: '测试银行', payee_account: '62220001',
      payee_name: '收款人', payee_bank: '测试银行', debit_credit: '借', amount: 1000, balance_after: 9000,
      channel: '手机银行', summary: '转账', region: '湖南长沙', review_status: 'pending', review_note: '',
      provenance: 'model_suggested', source: { source_file_id: 'FILE-1', page_number: 3, sheet_name: '流水明细', row_number: 8 },
    }] as any,
    total: 1,
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '流水校核' }))

  expect(await screen.findByText('数据来源')).toBeInTheDocument()
  expect(screen.getByText(/flow\.csv/)).toBeInTheDocument()
  expect(screen.getByText(/第3页/)).toBeInTheDocument()
  expect(screen.getByText(/流水明细/)).toBeInTheDocument()
  expect(screen.getByText(/第8行/)).toBeInTheDocument()
})

test('creating a case selects it and opens material intake', async () => {
  vi.mocked(api.createCase).mockResolvedValue({
    case_id: 'CASE-2', case_number: 'A-002', name: '新案件', status: 'active', created_at: '2026-07-22',
    victims: [],
  } as any)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '案件中心' }))
  fireEvent.change(screen.getByPlaceholderText('案件编号'), { target: { value: 'A-002' } })
  fireEvent.change(screen.getByPlaceholderText('案件名称'), { target: { value: '新案件' } })
  fireEvent.click(screen.getByRole('button', { name: '建立案件' }))

  expect(await screen.findByRole('heading', { name: '材料接收' })).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: '' })).toHaveValue('CASE-2')
})
