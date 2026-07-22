import type { Transaction } from "./types";

export function selectionForTransaction(transaction: Transaction | null) {
  return {
    selectedTx: transaction,
    selectedNode: null,
    selectedEdge: transaction
      ? `${transaction.payer_account}>${transaction.payee_account}`
      : null,
  };
}
