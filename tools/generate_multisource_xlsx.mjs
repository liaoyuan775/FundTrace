import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(process.argv[2]);
const artifactModule = process.argv[3];
const artifactTool = artifactModule
  ? await import(pathToFileURL(path.resolve(artifactModule)).href)
  : await import("@oai/artifact-tool");
const { SpreadsheetFile, Workbook } = artifactTool;
const outputDir = path.join(root, "materials");
const oracleDir = path.join(root, "oracle");
const truth = JSON.parse(await fs.readFile(path.join(oracleDir, "ground_truth.json"), "utf8"));
const distribution = JSON.parse(await fs.readFile(path.join(oracleDir, "distribution.json"), "utf8"));
const byId = new Map(truth.transactions.map((item) => [item.transaction_id, item]));

const variants = {
  "中国农业银行长沙分行_账户交易流水_20260618.xlsx": {
    sheetName: "交易明细",
    headers: ["交易日期", "交易流水号", "付款账号", "付款户名", "付款行", "收款账号", "收款户名", "收款行", "借贷标志", "币种", "交易金额", "交易后余额", "交易渠道", "摘要", "地区", "交易类型"],
    dateStyle: "date",
    amountStyle: "number",
  },
  "聚合支付商户结算明细_20260618.xlsx": {
    sheetName: "支付账单",
    headers: ["完成时间", "商户订单号", "付款方账号", "付款方户名", "付款方银行", "收款方账号", "收款方户名", "收款方银行", "方向", "货币", "支付金额", "账户余额", "支付方式", "用途", "发生地", "业务类型"],
    dateStyle: "text",
    amountStyle: "currencyText",
  },
};

function rowValues(item, variant) {
  const when = new Date(`${item.transaction_time}Z`);
  const account = (value) => `\u200B${value}`;
  return [
    variant.dateStyle === "date" ? when : item.transaction_time.replace("T", "/"),
    item.serial_number,
    account(item.payer_account),
    item.payer_name,
    item.payer_bank,
    account(item.payee_account),
    item.payee_name,
    item.payee_bank,
    item.debit_credit,
    item.currency,
    variant.amountStyle === "number" ? item.amount : `¥${item.amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
    variant.amountStyle === "number" ? item.balance_after : `¥${item.balance_after.toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
    item.channel,
    item.summary,
    item.region,
    item.transaction_type,
  ];
}

await fs.mkdir(outputDir, { recursive: true });
for (const [filename, variant] of Object.entries(variants)) {
  const spec = distribution.find((item) => item.filename === filename);
  if (!spec) throw new Error(`Missing distribution for ${filename}`);
  const rows = spec.transaction_ids.map((transactionId) => rowValues(byId.get(transactionId), variant));
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(variant.sheetName);
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const endRow = rows.length + 1;
  const range = sheet.getRange(`A1:P${endRow}`);
  range.values = [variant.headers, ...rows];
  range.format.font = { name: "Microsoft YaHei", size: 10, color: "#1A242C" };
  range.format.borders = { preset: "all", style: "thin", color: "#C8D2D9" };
  range.format.rowHeight = 22;
  const header = sheet.getRange("A1:P1");
  header.format.fill = "#173B57";
  header.format.font = { name: "Microsoft YaHei", size: 10, bold: true, color: "#FFFFFF" };
  header.format.rowHeight = 28;
  header.format.wrapText = true;
  sheet.getRange(`A2:A${endRow}`).format.numberFormat = variant.dateStyle === "date" ? "yyyy-mm-dd hh:mm:ss" : "@";
  sheet.getRange(`B2:H${endRow}`).format.numberFormat = "@";
  if (variant.amountStyle === "number") {
    sheet.getRange(`K2:L${endRow}`).format.numberFormat = "¥#,##0.00";
  } else {
    sheet.getRange(`K2:L${endRow}`).format.numberFormat = "@";
  }
  const widthsPx = [165, 175, 185, 240, 205, 185, 240, 205, 85, 70, 110, 110, 115, 135, 105, 95];
  widthsPx.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, endRow, 1).format.columnWidthPx = width;
  });
  sheet.tables.add(`A1:P${endRow}`, true, `Transactions${filename.startsWith("中国农业") ? "Bank" : "Pay"}`);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const outputPath = path.join(outputDir, filename);
  await output.save(outputPath);
  await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
}
