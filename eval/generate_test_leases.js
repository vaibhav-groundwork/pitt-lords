const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  Table, TableRow, TableCell, WidthType, BorderStyle,
} = require("docx");

const USLETTER = { width: 12240, height: 15840 };

function para(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, bold: opts.bold || false })],
    spacing: { after: 200 },
  });
}

function heading(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { after: 200 } });
}

function buildDoc(paragraphs) {
  return new Document({
    sections: [{ properties: { page: { size: USLETTER } }, children: paragraphs }],
  });
}

async function write(filename, paragraphs) {
  const doc = buildDoc(paragraphs);
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(`eval/test_leases/${filename}`, buf);
  console.log(`wrote ${filename}`);
}

async function main() {
  // 1. waiver_compliant.docx
  await write("waiver_compliant.docx", [
    heading("Residential Lease Agreement"),
    para("This lease is for the property at 100 Test St, Pittsburgh, PA, for a term of one year beginning January 1, 2026 and ending December 31, 2026."),
    heading("Security Deposit"),
    para("Tenant shall pay a security deposit of $1,000.00, equal to one month's rent, upon signing this lease. This deposit shall be held in an escrow account at Dollar Bank, 340 Fourth Ave, Pittsburgh, PA. Landlord will notify Tenant in writing of this account within 10 days of deposit."),
    heading("Notice to Vacate"),
    para("Tenant agrees to waive the standard notice-to-quit period established under Section 501 of the Landlord and Tenant Act of 1951, and agrees that seven (7) days written notice shall be sufficient for either party to terminate this lease at its natural end."),
  ]);

  // 2. illegal_waiver.docx
  await write("illegal_waiver.docx", [
    heading("Residential Lease Agreement"),
    para("This lease is for the property at 200 Test St, Pittsburgh, PA, for a term of one year."),
    heading("Security Deposit Waiver"),
    para("Tenant agrees to pay a security deposit of $1,500.00. Tenant expressly waives any and all rights, protections, and requirements under 68 P.S. Section 511.1(f) and Section 512(d) of the Landlord and Tenant Act of 1951 relating to the security deposit, including any right to itemized deductions, interest, or the 30-day return requirement. Tenant agrees this waiver is binding regardless of any contrary provision of law."),
  ]);

  // 3. lead_disclosure_compliant.docx
  await write("lead_disclosure_compliant.docx", [
    heading("Residential Lease Agreement"),
    para("This lease is for the property at 300 Test St, Pittsburgh, PA, built in 1925, for a term of one year."),
    heading("Lead Warning Statement"),
    para("Housing built before 1978 may contain lead-based paint. Lead from paint, paint chips, and dust can pose health hazards if not managed properly. Lead exposure is especially harmful to young children and pregnant women. Before renting pre-1978 housing, lessors must disclose the presence of known lead-based paint and/or lead-based paint hazards in the dwelling."),
    para("Landlord discloses that Landlord has no knowledge of lead-based paint and/or lead-based paint hazards in the housing. Landlord has provided Tenant with the EPA-approved pamphlet 'Protect Your Family from Lead in Your Home.' No lead hazard evaluation reports are available."),
  ]);

  // 4. modification_blocked.docx
  await write("modification_blocked.docx", [
    heading("Residential Lease Agreement"),
    para("This lease is for the property at 400 Test St, Pittsburgh, PA, for a term of one year."),
    heading("Alterations"),
    para("Tenant may not make any modification, alteration, or change to the Premises for any reason, under any circumstance, without exception. All requests for modifications are automatically denied and will not be considered by Landlord under any condition, including modifications related to disability or medical need."),
  ]);

  // 5. table_layout.docx -- deposit/rent info ONLY in a table, no paragraph text
  const rentTable = new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [4500, 4500],
    rows: [
      new TableRow({
        children: [
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("Item", { bold: true })] }),
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("Amount", { bold: true })] }),
        ],
      }),
      new TableRow({
        children: [
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("Monthly Rent")] }),
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("$1,200.00")] }),
        ],
      }),
      new TableRow({
        children: [
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("Security Deposit (Year 1)")] }),
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("$2,400.00 (two months' rent)")] }),
        ],
      }),
      new TableRow({
        children: [
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("Lease Term")] }),
          new TableCell({ width: { size: 4500, type: WidthType.DXA }, children: [para("12 months")] }),
        ],
      }),
    ],
  });
  await write("table_layout.docx", [
    heading("Residential Lease Agreement"),
    para("This lease is for the property at 500 Test St, Pittsburgh, PA. Financial terms are set forth in the table below."),
    rentTable,
    para("All other terms of this lease are standard."),
  ]);

  // 6. sparse_minimal.docx -- deliberately bare, missing almost everything
  await write("sparse_minimal.docx", [
    heading("Residential Lease Agreement"),
    para("This lease is for the property at 600 Test St, Pittsburgh, PA, for a term of one year beginning January 1, 2026."),
    para("Rent is $900.00 per month, due on the first of each month."),
    para("Tenant shall keep the property in good condition."),
  ]);
}

main().catch((e) => { console.error(e); process.exit(1); });
