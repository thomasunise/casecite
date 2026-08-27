// Display labels for contract types returned by the contract-analysis API.

const CONTRACT_TYPE_LABELS: Record<string, string> = {
  nda: 'NDA',
  msa: 'MSA',
  saas: 'SaaS',
  employment: 'Employment',
  license: 'License',
  sow: 'SOW',
  other: 'Contract',
};

export function contractTypeLabel(type: string | null | undefined): string {
  if (!type) return 'Contract';
  return CONTRACT_TYPE_LABELS[type] || type;
}
