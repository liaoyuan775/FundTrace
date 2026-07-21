import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from './App'

vi.mock('./api', () => ({
  bootstrapDemo: vi.fn().mockResolvedValue({ case_id: 'CASE-DEMO' }),
  listCases: vi.fn().mockResolvedValue([]),
  getCase: vi.fn(), getGraph: vi.fn(), getTransactions: vi.fn(), listMaterials: vi.fn().mockResolvedValue([{ file_id: 'FILE-1', original_name: 'flow.csv', size: 10, sha256: 'abc', duplicate: false, status: 'uploaded' }]), listVersions: vi.fn(), listSeeds: vi.fn(),
  parseMaterial: vi.fn().mockResolvedValue({ material: { status: 'parsed', draft_count: 1 } }),
}))
vi.mock('./GraphCanvas', () => ({ default: () => <div data-testid="graph-canvas" /> }))

test('renders every investigation workspace and raw transaction baseline', () => {
  render(<App />)
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
