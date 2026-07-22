import { describe, expect, test } from "vitest";
import { selectionForTransaction } from "./selection-state";
import type { Transaction } from "./types";

describe("transaction selection", () => {
  test("keeps the transaction and focuses its graph edge", () => {
    const transaction = {
      transaction_id: "TX-1",
      payer_account: "A",
      payee_account: "B",
    } as Transaction;

    expect(selectionForTransaction(transaction)).toEqual({
      selectedTx: transaction,
      selectedNode: null,
      selectedEdge: "A>B",
    });
  });

  test("clears every selection for a null transaction", () => {
    expect(selectionForTransaction(null)).toEqual({
      selectedTx: null,
      selectedNode: null,
      selectedEdge: null,
    });
  });
});
