import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from './App'

vi.mock('./api', () => ({
  bootstrapDemo: vi.fn().mockResolvedValue({ case_id: 'CASE-DEMO' }),
  listCases: vi.fn().mockResolvedValue([]),
  getCase: vi.fn(), getGraph: vi.fn(), getTransactions: vi.fn(), listMaterials: vi.fn(), listVersions: vi.fn(), listSeeds: vi.fn(),
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
