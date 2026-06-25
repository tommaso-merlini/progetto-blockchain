export type PendingUpdate = {
  role: "proposer" | "responder" | string;
  next_index?: number;
  own_amount: number;
  peer_amount: number;
};

export type ChannelCommitmentStatus = {
  tx_index: number;
  own_amount: number;
  peer_amount: number;
  capacity: number;
  is_current: boolean;
};

export type ChannelStatus = {
  current_index: number;
  own_amount: number;
  peer_amount: number;
  capacity: number;
  commitments: ChannelCommitmentStatus[];
  revoked_peer_state_indices: number[];
  peer_url?: string;
  pending_update?: PendingUpdate;
};

export type StatusResponse = Record<string, ChannelStatus>;

export type PendingFundingStatus = {
  role: "proposer" | "responder" | string;
  own_amount: number;
  peer_amount: number;
  capacity: number;
  peer_url?: string;
};

export type PendingFundingsResponse = Record<string, PendingFundingStatus>;

export type FundingContribution = {
  public_key: string;
  amount: number;
};

export type FundingTransaction = {
  contributions: FundingContribution[];
  output: {
    amount: number;
    public_keys: string[];
    required_signatures: number;
  };
};

export type CommitmentTransaction = {
  funding_id: string;
  tx_index: number;
  owner: string;
  own_amount: number;
  peer_amount: number;
  revocation_hash: string;
  signatures: Record<string, string>;
};

export type PendingClose = {
  commitment: CommitmentTransaction;
  published_at_block: number;
  deadline_block: number;
};

export type MultisigStatus = {
  funding_id: string;
  funding: FundingTransaction;
  spent: boolean;
  pending_close: PendingClose | null;
};

export type BlockchainStatus = {
  block_number: number;
  multisigs: Record<string, MultisigStatus>;
  balances: Record<string, number>;
};

async function readError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `${response.status} ${response.statusText}`;
  }

  try {
    const body = JSON.parse(text) as { error?: unknown };
    if (body.error) {
      return String(body.error);
    }
  } catch {
    return text;
  }

  return text;
}

export async function apiGetText(apiBaseUrl: string, path: string): Promise<string> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.text();
}

export async function apiGetJson<T>(apiBaseUrl: string, path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(
  apiBaseUrl: string,
  path: string,
  payload: unknown,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json() as Promise<T>;
}
