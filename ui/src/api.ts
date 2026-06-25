export type PendingUpdate = {
  role: "proposer" | "responder" | string;
  next_index?: number;
  own_amount: number;
  peer_amount: number;
};

export type ChannelStatus = {
  current_index: number;
  own_amount: number;
  peer_amount: number;
  peer_url?: string;
  pending_update?: PendingUpdate;
};

export type StatusResponse = Record<string, ChannelStatus>;

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
