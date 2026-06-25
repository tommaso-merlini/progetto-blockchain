import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Check,
  CheckCircle2,
  Database,
  Lock,
  Plus,
  RefreshCw,
  Send,
  X,
} from "lucide-react";
import {
  BlockchainStatus,
  ChannelStatus,
  MultisigStatus,
  PendingFundingStatus,
  PendingFundingsResponse,
  StatusResponse,
  apiGetJson,
  apiGetText,
  apiPost,
} from "./api";
import { Alert } from "./components/ui/alert";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";

const API_URL_STORAGE_KEY = "lightning-dashboard-api-url";
const LAST_PEER_URL_STORAGE_KEY = "lightning-dashboard-last-peer-url";
const CHANNEL_PEER_URLS_STORAGE_KEY = "lightning-dashboard-channel-peer-urls";
const defaultApiUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";
const peerUrlInputListId = "peer-url-options";

type Notice = {
  tone: "success" | "error";
  message: string;
};

type FundForm = {
  ownAmount: string;
  peerAmount: string;
  peerUrl: string;
};

type UpdateForm = {
  fundingId: string;
  ownAmount: string;
  peerAmount: string;
  peerUrl: string;
};

type AcceptForm = {
  fundingId: string;
  proposerUrl: string;
};

type AcceptFundingForm = {
  fundingId: string;
  proposerUrl: string;
};

type CloseChannelResponse = {
  funding_id: string;
  published_at_block: number;
  deadline_block: number;
};

type FinalizeCloseResponse = {
  funding_id: string;
  owner: string;
  peer: string;
  owner_amount: number;
  peer_amount: number;
};

type ActiveDialog = "propose" | "accept" | "acceptFunding" | null;
type ChannelPeerUrls = Record<string, string>;

function normalizeUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function parseWholeNumber(value: string, label: string): number {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    throw new Error(`${label} must be a non-negative integer.`);
  }
  return Number(trimmed);
}

function shortId(value: string): string {
  if (value.length <= 20) {
    return value;
  }
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}

function chainStatusLabel(multisig?: MultisigStatus): string {
  if (!multisig) {
    return "Not registered";
  }
  if (multisig.spent) {
    return "Finalized";
  }
  if (multisig.pending_close) {
    return "Closing";
  }
  return "Open";
}

function channelEntries(status: StatusResponse): Array<[string, ChannelStatus]> {
  return Object.entries(status).sort(([left], [right]) => left.localeCompare(right));
}

function readChannelPeerUrls(): ChannelPeerUrls {
  try {
    const stored = JSON.parse(
      localStorage.getItem(CHANNEL_PEER_URLS_STORAGE_KEY) ?? "{}",
    );
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(stored).filter((entry): entry is [string, string] => {
        return typeof entry[1] === "string";
      }),
    );
  } catch {
    return {};
  }
}

function channelPeerUrlKey(apiUrl: string, channelId: string): string {
  return `${apiUrl}\n${channelId}`;
}

function Field({
  children,
  htmlFor,
  label,
}: {
  children: ReactNode;
  htmlFor: string;
  label: string;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function MetricCard({
  label,
  title,
  value,
}: {
  label: string;
  title?: string;
  value: ReactNode;
}) {
  return (
    <Card className="min-w-0">
      <CardContent className="p-4">
        <span className="block text-xs font-extrabold uppercase tracking-normal text-slate-500">
          {label}
        </span>
        <strong
          className="mt-2 block overflow-hidden text-2xl font-extrabold text-ellipsis whitespace-nowrap"
          title={title}
        >
          {value}
        </strong>
      </CardContent>
    </Card>
  );
}

function Modal({
  children,
  onClose,
  title,
}: {
  children: ReactNode;
  onClose: () => void;
  title: string;
}) {
  useEffect(() => {
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        aria-labelledby="action-dialog-title"
        aria-modal="true"
        className="max-h-[min(720px,calc(100vh_-_32px))] w-[min(440px,100%)] overflow-auto rounded-lg border border-slate-200 bg-white text-slate-950 shadow-xl"
        role="dialog"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
          <h2
            className="text-base font-extrabold leading-none text-slate-800"
            id="action-dialog-title"
          >
            {title}
          </h2>
          <Button
            aria-label="Close"
            size="icon"
            type="button"
            variant="ghost"
            onClick={onClose}
          >
            <X className="size-4" />
          </Button>
        </div>
        {children}
      </section>
    </div>
  );
}

function App() {
  const [apiUrl, setApiUrl] = useState(() => {
    return localStorage.getItem(API_URL_STORAGE_KEY) ?? defaultApiUrl;
  });
  const [publicKey, setPublicKey] = useState("");
  const [status, setStatus] = useState<StatusResponse>({});
  const [pendingFundings, setPendingFundings] = useState<PendingFundingsResponse>(
    {},
  );
  const [blockchainStatus, setBlockchainStatus] =
    useState<BlockchainStatus | null>(null);
  const [blockchainError, setBlockchainError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [channelPeerUrls, setChannelPeerUrls] = useState<ChannelPeerUrls>(() =>
    readChannelPeerUrls(),
  );
  const [lastPeerUrl, setLastPeerUrl] = useState(() => {
    return localStorage.getItem(LAST_PEER_URL_STORAGE_KEY) ?? "";
  });
  const [fundForm, setFundForm] = useState<FundForm>(() => ({
    ownAmount: "50",
    peerAmount: "50",
    peerUrl: localStorage.getItem(LAST_PEER_URL_STORAGE_KEY) ?? "",
  }));
  const [updateForm, setUpdateForm] = useState<UpdateForm>(() => ({
    fundingId: "",
    ownAmount: "",
    peerAmount: "",
    peerUrl: localStorage.getItem(LAST_PEER_URL_STORAGE_KEY) ?? "",
  }));
  const [acceptForm, setAcceptForm] = useState<AcceptForm>(() => ({
    fundingId: "",
    proposerUrl: localStorage.getItem(LAST_PEER_URL_STORAGE_KEY) ?? "",
  }));
  const [acceptFundingForm, setAcceptFundingForm] = useState<AcceptFundingForm>(
    () => ({
      fundingId: "",
      proposerUrl: localStorage.getItem(LAST_PEER_URL_STORAGE_KEY) ?? "",
    }),
  );
  const [activeDialog, setActiveDialog] = useState<ActiveDialog>(null);

  const normalizedApiUrl = useMemo(() => normalizeUrl(apiUrl), [apiUrl]);
  const channels = useMemo(() => channelEntries(status), [status]);
  const pendingFundingEntries = useMemo(() => {
    return Object.entries(pendingFundings).sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }, [pendingFundings]);
  const multisigs = useMemo(() => {
    return Object.entries(blockchainStatus?.multisigs ?? {}).sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }, [blockchainStatus]);
  const pendingCloseCount = useMemo(() => {
    return multisigs.filter(([, multisig]) => {
      return Boolean(multisig.pending_close && !multisig.spent);
    }).length;
  }, [multisigs]);
  const knownPeerUrls = useMemo(() => {
    const urls = new Set<string>();
    if (lastPeerUrl) {
      urls.add(lastPeerUrl);
    }
    for (const peerUrl of Object.values(channelPeerUrls)) {
      if (peerUrl) {
        urls.add(peerUrl);
      }
    }
    for (const [, channel] of channels) {
      const peerUrl = normalizeUrl(channel.peer_url ?? "");
      if (peerUrl) {
        urls.add(peerUrl);
      }
    }
    for (const [, pending] of pendingFundingEntries) {
      const peerUrl = normalizeUrl(pending.peer_url ?? "");
      if (peerUrl) {
        urls.add(peerUrl);
      }
    }
    return Array.from(urls).sort();
  }, [channelPeerUrls, channels, lastPeerUrl, pendingFundingEntries]);

  function getSuggestedPeerUrl(channelId: string, channel?: ChannelStatus): string {
    const statusPeerUrl = normalizeUrl(channel?.peer_url ?? "");
    if (statusPeerUrl) {
      return statusPeerUrl;
    }
    return (
      channelPeerUrls[channelPeerUrlKey(normalizedApiUrl, channelId)] ?? lastPeerUrl
    );
  }

  function rememberPeerUrl(channelId: string | null, value: string) {
    const peerUrl = normalizeUrl(value);
    if (!peerUrl) {
      return;
    }

    localStorage.setItem(LAST_PEER_URL_STORAGE_KEY, peerUrl);
    setLastPeerUrl(peerUrl);

    if (!channelId || !normalizedApiUrl) {
      return;
    }

    setChannelPeerUrls((current) => {
      const key = channelPeerUrlKey(normalizedApiUrl, channelId);
      if (current[key] === peerUrl) {
        return current;
      }

      const next = { ...current, [key]: peerUrl };
      localStorage.setItem(CHANNEL_PEER_URLS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }

  async function refreshBlockchain(nextApiUrl = normalizedApiUrl) {
    if (!nextApiUrl) {
      setBlockchainStatus(null);
      setBlockchainError("Set a node API URL first.");
      return;
    }

    try {
      const nextBlockchainStatus = await apiGetJson<BlockchainStatus>(
        nextApiUrl,
        "/client/blockchain/status",
      );
      setBlockchainStatus(nextBlockchainStatus);
      setBlockchainError(null);
    } catch (error) {
      setBlockchainStatus(null);
      setBlockchainError(error instanceof Error ? error.message : String(error));
    }
  }

  async function refresh(
    nextApiUrl = normalizedApiUrl,
    options: { quiet?: boolean } = {},
  ) {
    if (!nextApiUrl) {
      setNotice({ tone: "error", message: "Set a node API URL first." });
      return;
    }

    setIsLoading(true);
    if (!options.quiet) {
      setNotice(null);
    }
    try {
      const [nextPublicKey, nextStatus, nextPendingFundings] = await Promise.all([
        apiGetText(nextApiUrl, "/public-key"),
        apiGetJson<StatusResponse>(nextApiUrl, "/status"),
        apiGetJson<PendingFundingsResponse>(
          nextApiUrl,
          "/client/pending-fundings",
        ),
      ]);
      setPublicKey(nextPublicKey.trim());
      setStatus(nextStatus);
      setPendingFundings(nextPendingFundings);
      localStorage.setItem(API_URL_STORAGE_KEY, nextApiUrl);
      setApiUrl(nextApiUrl);
      await refreshBlockchain(nextApiUrl);
    } catch (error) {
      setPublicKey("");
      setStatus({});
      setPendingFundings({});
      setBlockchainStatus(null);
      setBlockchainError(null);
      setNotice({
        tone: "error",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!normalizedApiUrl) {
      return;
    }

    const entries = channels
      .map(([channelId, channel]) => {
        return [channelId, normalizeUrl(channel.peer_url ?? "")] as const;
      })
      .filter((entry) => entry[1]);

    if (entries.length === 0) {
      return;
    }

    setChannelPeerUrls((current) => {
      let changed = false;
      const next = { ...current };

      for (const [channelId, peerUrl] of entries) {
        const key = channelPeerUrlKey(normalizedApiUrl, channelId);
        if (next[key] !== peerUrl) {
          next[key] = peerUrl;
          changed = true;
        }
      }

      if (!changed) {
        return current;
      }

      localStorage.setItem(CHANNEL_PEER_URLS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, [channels, normalizedApiUrl]);

  useEffect(() => {
    if (!channels[0]) {
      return;
    }

    if (!updateForm.fundingId) {
      const [channelId, channel] = channels[0];
      setUpdateForm((current) => ({
        ...current,
        fundingId: channelId,
        peerUrl: current.peerUrl || getSuggestedPeerUrl(channelId, channel),
      }));
    }
    if (!acceptForm.fundingId) {
      const [channelId, channel] = channels[0];
      setAcceptForm((current) => ({
        ...current,
        fundingId: channelId,
        proposerUrl: current.proposerUrl || getSuggestedPeerUrl(channelId, channel),
      }));
    }
  }, [
    acceptForm.fundingId,
    channelPeerUrls,
    channels,
    lastPeerUrl,
    normalizedApiUrl,
    updateForm.fundingId,
  ]);

  async function runAction<T>(action: () => Promise<T>, success: (result: T) => string) {
    setIsLoading(true);
    setNotice(null);
    try {
      const result = await action();
      await refresh(normalizedApiUrl, { quiet: true });
      setNotice({ tone: "success", message: success(result) });
    } catch (error) {
      setNotice({
        tone: "error",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setIsLoading(false);
    }
  }

  function handleApiSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void refresh(normalizeUrl(apiUrl));
  }

  function handleFund(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const peerUrl = normalizeUrl(fundForm.peerUrl);
    void runAction(
      () =>
        apiPost<{ funding_id: string; status: string }>(
          normalizedApiUrl,
          "/client/fund",
          {
            own_amount: parseWholeNumber(fundForm.ownAmount, "Local amount"),
            peer_amount: parseWholeNumber(fundForm.peerAmount, "Remote amount"),
            peer_url: peerUrl,
            own_url: normalizedApiUrl,
          },
        ),
      (result) => {
        rememberPeerUrl(result.funding_id, peerUrl);
        setFundForm((current) => ({ ...current, peerUrl }));
        return `Funding proposal sent: ${shortId(result.funding_id)}`;
      },
    );
  }

  function handleAcceptFunding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const proposerUrl = normalizeUrl(acceptFundingForm.proposerUrl);
    void runAction(
      () =>
        apiPost<{ status: string; funding_id: string }>(
          normalizedApiUrl,
          "/client/accept-funding",
          {
            funding_id: acceptFundingForm.fundingId,
            proposer_url: proposerUrl,
          },
        ),
      (result) => {
        rememberPeerUrl(result.funding_id, proposerUrl);
        setAcceptFundingForm((current) => ({ ...current, proposerUrl }));
        setActiveDialog(null);
        return `Funding accepted: ${shortId(result.funding_id)}`;
      },
    );
  }

  function handleProposeUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const peerUrl = normalizeUrl(updateForm.peerUrl);
    void runAction(
      () =>
        apiPost<{ status: string }>(normalizedApiUrl, "/client/propose-update", {
          funding_id: updateForm.fundingId,
          own_amount: parseWholeNumber(updateForm.ownAmount, "New local balance"),
          peer_amount: parseWholeNumber(updateForm.peerAmount, "New remote balance"),
          peer_url: peerUrl,
          own_url: normalizedApiUrl,
        }),
      () => {
        rememberPeerUrl(updateForm.fundingId, peerUrl);
        setUpdateForm((current) => ({ ...current, peerUrl }));
        setActiveDialog(null);
        return "Update proposal sent.";
      },
    );
  }

  function handleAcceptUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const proposerUrl = normalizeUrl(acceptForm.proposerUrl);
    void runAction(
      () =>
        apiPost<{ status: string }>(normalizedApiUrl, "/client/accept-update", {
          funding_id: acceptForm.fundingId,
          proposer_url: proposerUrl,
        }),
      () => {
        rememberPeerUrl(acceptForm.fundingId, proposerUrl);
        setAcceptForm((current) => ({ ...current, proposerUrl }));
        setActiveDialog(null);
        return "Update accepted.";
      },
    );
  }

  function handleCloseChannel(channelId: string, txIndex: number) {
    void runAction(
      () =>
        apiPost<CloseChannelResponse>(normalizedApiUrl, "/client/close-channel", {
          funding_id: channelId,
          tx_index: txIndex,
        }),
      (result) => {
        return `Close published at block #${result.published_at_block}; finalizable at block #${result.deadline_block}.`;
      },
    );
  }

  function handleFinalizeClose(channelId: string) {
    void runAction(
      () =>
        apiPost<FinalizeCloseResponse>(normalizedApiUrl, "/client/finalize-close", {
          funding_id: channelId,
        }),
      (result) => {
        return `Close finalized: local owner received ${result.owner_amount}, peer received ${result.peer_amount}.`;
      },
    );
  }

  function openProposeDialog(channelId: string, channel: ChannelStatus) {
    setUpdateForm((current) => ({
      ...current,
      fundingId: channelId,
      ownAmount: String(channel.own_amount),
      peerAmount: String(channel.peer_amount),
      peerUrl: getSuggestedPeerUrl(channelId, channel),
    }));
    setActiveDialog("propose");
  }

  function openAcceptDialog(channelId: string, channel: ChannelStatus) {
    setAcceptForm((current) => ({
      ...current,
      fundingId: channelId,
      proposerUrl: getSuggestedPeerUrl(channelId, channel),
    }));
    setActiveDialog("accept");
  }

  function openAcceptFundingDialog(
    fundingId: string,
    pending: PendingFundingStatus,
  ) {
    setAcceptFundingForm((current) => ({
      ...current,
      fundingId,
      proposerUrl: normalizeUrl(pending.peer_url ?? "") || current.proposerUrl,
    }));
    setActiveDialog("acceptFunding");
  }

  return (
    <main className="mx-auto w-[min(1180px,calc(100%_-_32px))] py-7 text-slate-900 max-md:w-[min(680px,calc(100%_-_24px))] max-md:py-5">
      <datalist id={peerUrlInputListId}>
        {knownPeerUrls.map((peerUrl) => (
          <option key={peerUrl} value={peerUrl} />
        ))}
      </datalist>
      <header className="flex items-end justify-between gap-6 border-b border-slate-200 pb-5 max-md:grid max-md:items-stretch">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-normal text-slate-500">
            Lightning Network
          </p>
          <h1 className="mt-1 text-5xl font-extrabold leading-none text-slate-950 max-sm:text-3xl">
            Node Dashboard
          </h1>
        </div>
        <form className="w-[min(460px,100%)]" onSubmit={handleApiSubmit}>
          <Field htmlFor="api-url" label="Node API">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 max-md:grid-cols-1">
              <Input
                id="api-url"
                value={apiUrl}
                onChange={(event) => setApiUrl(event.target.value)}
                placeholder="http://127.0.0.1:8001"
              />
              <Button type="submit" disabled={isLoading}>
                <RefreshCw className="size-4" />
                Refresh
              </Button>
            </div>
          </Field>
        </form>
      </header>

      {notice && (
        <Alert
          className="mt-5"
          variant={notice.tone === "success" ? "success" : "destructive"}
        >
          {notice.message}
        </Alert>
      )}

      <section
        className="mt-5 grid grid-cols-5 gap-3 max-xl:grid-cols-3 max-lg:grid-cols-2 max-md:grid-cols-1"
        aria-label="Node summary"
      >
        <MetricCard
          label="Public key"
          title={publicKey}
          value={publicKey ? shortId(publicKey) : "Unavailable"}
        />
        <MetricCard label="Channels" value={channels.length} />
        <MetricCard label="Pending fundings" value={pendingFundingEntries.length} />
        <MetricCard
          label="Pending updates"
          value={channels.filter(([, channel]) => channel.pending_update).length}
        />
        <MetricCard
          label="Block height"
          value={blockchainStatus ? `#${blockchainStatus.block_number}` : "Unavailable"}
        />
      </section>

      <section className="mt-6 grid grid-cols-[minmax(0,1fr)_360px] items-start gap-5 max-md:grid-cols-1">
        <div className="grid gap-3">
          {pendingFundingEntries.length > 0 && (
            <div className="grid gap-3">
              <h2 className="text-base font-extrabold text-slate-800">
                Funding proposals
              </h2>
              {pendingFundingEntries.map(([fundingId, pending]) => {
                const peerUrl = normalizeUrl(pending.peer_url ?? "");
                const isReceived = pending.role !== "proposer";
                return (
                  <Card key={fundingId}>
                    <CardContent className="grid gap-4 p-4">
                      <div className="flex items-start justify-between gap-4 max-sm:grid">
                        <div>
                          <span className="block text-xs font-extrabold uppercase tracking-normal text-slate-500">
                            Funding
                          </span>
                          <strong
                            className="mt-1 block text-lg font-extrabold [overflow-wrap:anywhere]"
                            title={fundingId}
                          >
                            {shortId(fundingId)}
                          </strong>
                          {peerUrl && (
                            <span
                              className="mt-1 block max-w-[min(460px,100%)] overflow-hidden text-sm font-bold text-slate-500 text-ellipsis whitespace-nowrap"
                              title={peerUrl}
                            >
                              {peerUrl}
                            </span>
                          )}
                        </div>
                        <div className="min-w-24 rounded-full bg-amber-100 px-3 py-1.5 text-center text-sm font-extrabold text-amber-900 max-sm:w-max">
                          {isReceived ? "Received" : "Sent"}
                        </div>
                      </div>
                      <dl className="m-0 grid grid-cols-3 gap-2.5 max-sm:grid-cols-1">
                        <div className="border-l-4 border-slate-400 pl-3">
                          <dt className="text-xs font-extrabold uppercase text-slate-500">
                            Local
                          </dt>
                          <dd className="mt-1 text-xl font-extrabold">
                            {pending.own_amount}
                          </dd>
                        </div>
                        <div className="border-l-4 border-slate-400 pl-3">
                          <dt className="text-xs font-extrabold uppercase text-slate-500">
                            Remote
                          </dt>
                          <dd className="mt-1 text-xl font-extrabold">
                            {pending.peer_amount}
                          </dd>
                        </div>
                        <div className="border-l-4 border-slate-400 pl-3">
                          <dt className="text-xs font-extrabold uppercase text-slate-500">
                            Capacity
                          </dt>
                          <dd className="mt-1 text-xl font-extrabold">
                            {pending.capacity}
                          </dd>
                        </div>
                      </dl>
                      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-1">
                        <Button
                          size="sm"
                          type="button"
                          variant="secondary"
                          disabled={isLoading || !isReceived}
                          onClick={() => openAcceptFundingDialog(fundingId, pending)}
                        >
                          <Check className="size-4" />
                          Accept funding
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}

          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-extrabold text-slate-800">Channels</h2>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void refresh()}
              disabled={isLoading}
            >
              <RefreshCw className="size-4" />
              Refresh
            </Button>
          </div>

          {channels.length === 0 ? (
            <Card>
              <CardContent className="p-6 font-bold text-slate-500">
                No active channels for this node.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-3">
              {channels.map(([channelId, channel]) => {
                const capacity = channel.own_amount + channel.peer_amount;
                const pending = channel.pending_update;
                const peerUrl = getSuggestedPeerUrl(channelId, channel);
                const multisig = blockchainStatus?.multisigs[channelId];
                const pendingClose = multisig?.pending_close;
                const isChainBlocked = Boolean(pendingClose || multisig?.spent);
                const canFinalize = Boolean(
                  blockchainStatus &&
                    pendingClose &&
                    !multisig?.spent &&
                    blockchainStatus.block_number >= pendingClose.deadline_block,
                );
                const blocksUntilFinalize =
                  blockchainStatus && pendingClose
                    ? Math.max(
                        pendingClose.deadline_block - blockchainStatus.block_number,
                        0,
                      )
                    : null;
                return (
                  <Card key={channelId}>
                    <CardContent className="grid gap-4 p-4">
                      <div className="flex items-start justify-between gap-4 max-sm:grid">
                        <div>
                          <span className="block text-xs font-extrabold uppercase tracking-normal text-slate-500">
                            Channel
                          </span>
                          <strong
                            className="mt-1 block text-lg font-extrabold [overflow-wrap:anywhere]"
                            title={channelId}
                          >
                            {shortId(channelId)}
                          </strong>
                          {peerUrl && (
                            <span
                              className="mt-1 block max-w-[min(460px,100%)] overflow-hidden text-sm font-bold text-slate-500 text-ellipsis whitespace-nowrap"
                              title={peerUrl}
                            >
                              {peerUrl}
                            </span>
                          )}
                        </div>
                        <div className="min-w-12 rounded-full bg-slate-100 px-3 py-1.5 text-center font-extrabold text-slate-700 max-sm:w-max">
                          #{channel.current_index}
                        </div>
                      </div>
                      <dl className="m-0 grid grid-cols-3 gap-2.5 max-sm:grid-cols-1">
                        <div className="border-l-4 border-slate-400 pl-3">
                          <dt className="text-xs font-extrabold uppercase text-slate-500">
                            Local
                          </dt>
                          <dd className="mt-1 text-xl font-extrabold">
                            {channel.own_amount}
                          </dd>
                        </div>
                        <div className="border-l-4 border-slate-400 pl-3">
                          <dt className="text-xs font-extrabold uppercase text-slate-500">
                            Remote
                          </dt>
                          <dd className="mt-1 text-xl font-extrabold">
                            {channel.peer_amount}
                          </dd>
                        </div>
                        <div className="border-l-4 border-slate-400 pl-3">
                          <dt className="text-xs font-extrabold uppercase text-slate-500">
                            Capacity
                          </dt>
                          <dd className="mt-1 text-xl font-extrabold">{capacity}</dd>
                        </div>
                      </dl>
                      {pending && (
                        <div className="grid gap-1 rounded-md bg-amber-100 px-3 py-2.5 text-amber-900">
                          <span className="font-bold">
                            Pending {pending.role === "proposer" ? "sent" : "received"}
                          </span>
                          <strong className="text-amber-950">
                            {pending.own_amount} / {pending.peer_amount}
                          </strong>
                          {pending.next_index !== undefined && (
                            <small className="font-bold">
                              Next index #{pending.next_index}
                            </small>
                          )}
                        </div>
                      )}
                      <div className="grid gap-1 rounded-md bg-slate-100 px-3 py-2.5 text-slate-700">
                        <span className="font-bold">
                          On-chain: {chainStatusLabel(multisig)}
                        </span>
                        {pendingClose ? (
                          <small className="font-bold">
                            Published at block #{pendingClose.published_at_block};
                            deadline #{pendingClose.deadline_block}
                            {blocksUntilFinalize !== null && blocksUntilFinalize > 0
                              ? ` (${blocksUntilFinalize} blocks left)`
                              : ""}
                          </small>
                        ) : (
                          <small className="font-bold">
                            {multisig
                              ? `${multisig.funding.output.amount} total capacity locked`
                              : "Waiting for chain record."}
                          </small>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-1">
                        <Button
                          size="sm"
                          type="button"
                          variant="outline"
                          disabled={isLoading || Boolean(pending) || isChainBlocked}
                          onClick={() => openProposeDialog(channelId, channel)}
                        >
                          <Send className="size-4" />
                          Propose update
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          variant="secondary"
                          disabled={
                            isLoading || pending?.role !== "responder" || isChainBlocked
                          }
                          onClick={() => openAcceptDialog(channelId, channel)}
                        >
                          <Check className="size-4" />
                          Accept update
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          variant="outline"
                          disabled={
                            isLoading ||
                            Boolean(pending) ||
                            isChainBlocked ||
                            !multisig
                          }
                          title="Publish the current signed commitment to the mock blockchain"
                          onClick={() =>
                            handleCloseChannel(channelId, channel.current_index)
                          }
                        >
                          <Lock className="size-4" />
                          Publish close
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          variant="secondary"
                          disabled={isLoading || !canFinalize}
                          title={
                            pendingClose
                              ? "Finalize after the challenge period expires"
                              : "Publish a close before finalizing"
                          }
                          onClick={() => handleFinalizeClose(channelId)}
                        >
                          <CheckCircle2 className="size-4" />
                          Finalize
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        <div className="grid gap-3">
          <Card>
            <form onSubmit={handleFund}>
              <CardHeader>
                <CardTitle>Open channel</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3">
                <Field htmlFor="fund-own-amount" label="Local amount">
                  <Input
                    id="fund-own-amount"
                    inputMode="numeric"
                    min="0"
                    type="number"
                    value={fundForm.ownAmount}
                    onChange={(event) =>
                      setFundForm((current) => ({
                        ...current,
                        ownAmount: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field htmlFor="fund-peer-amount" label="Remote amount">
                  <Input
                    id="fund-peer-amount"
                    inputMode="numeric"
                    min="0"
                    type="number"
                    value={fundForm.peerAmount}
                    onChange={(event) =>
                      setFundForm((current) => ({
                        ...current,
                        peerAmount: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field htmlFor="fund-peer-url" label="Peer URL">
                  <Input
                    id="fund-peer-url"
                    list={peerUrlInputListId}
                    value={fundForm.peerUrl}
                    onChange={(event) =>
                      setFundForm((current) => ({
                        ...current,
                        peerUrl: event.target.value,
                      }))
                    }
                    placeholder="http://127.0.0.1:8002"
                  />
                </Field>
                <Button className="mt-1" type="submit" disabled={isLoading}>
                  <Plus className="size-4" />
                  Open channel
                </Button>
              </CardContent>
            </form>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle>Mock blockchain</CardTitle>
              <Button
                aria-label="Refresh blockchain"
                size="icon"
                type="button"
                variant="ghost"
                disabled={isLoading}
                onClick={() => void refreshBlockchain()}
              >
                <RefreshCw className="size-4" />
              </Button>
            </CardHeader>
            <CardContent className="grid gap-3">
              {blockchainError ? (
                <div className="rounded-md bg-red-50 px-3 py-2.5 text-sm font-bold leading-6 text-red-800">
                  {blockchainError}
                </div>
              ) : blockchainStatus ? (
                <>
                  <dl className="m-0 grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-md bg-slate-100 px-2 py-2">
                      <dt className="text-xs font-extrabold uppercase text-slate-500">
                        Block
                      </dt>
                      <dd className="mt-1 font-extrabold">
                        #{blockchainStatus.block_number}
                      </dd>
                    </div>
                    <div className="rounded-md bg-slate-100 px-2 py-2">
                      <dt className="text-xs font-extrabold uppercase text-slate-500">
                        Multisigs
                      </dt>
                      <dd className="mt-1 font-extrabold">{multisigs.length}</dd>
                    </div>
                    <div className="rounded-md bg-slate-100 px-2 py-2">
                      <dt className="text-xs font-extrabold uppercase text-slate-500">
                        Pending
                      </dt>
                      <dd className="mt-1 font-extrabold">{pendingCloseCount}</dd>
                    </div>
                  </dl>

                  {multisigs.length === 0 ? (
                    <div className="rounded-md border border-dashed border-slate-300 px-3 py-3 text-sm font-bold text-slate-500">
                      No multisigs registered.
                    </div>
                  ) : (
                    <div className="grid gap-2">
                      {multisigs.map(([fundingId, multisig]) => {
                        const pendingClose = multisig.pending_close;
                        const canFinalize = Boolean(
                          pendingClose &&
                            !multisig.spent &&
                            blockchainStatus.block_number >=
                              pendingClose.deadline_block,
                        );
                        return (
                          <div
                            className="grid gap-2 rounded-md border border-slate-200 px-3 py-2.5"
                            key={fundingId}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <strong
                                  className="block overflow-hidden text-sm text-ellipsis whitespace-nowrap"
                                  title={fundingId}
                                >
                                  {shortId(fundingId)}
                                </strong>
                                <span className="mt-1 block text-xs font-extrabold uppercase text-slate-500">
                                  {chainStatusLabel(multisig)} - capacity{" "}
                                  {multisig.funding.output.amount}
                                </span>
                              </div>
                              <Database className="mt-0.5 size-4 shrink-0 text-slate-500" />
                            </div>
                            {pendingClose && (
                              <div className="flex items-center justify-between gap-2 rounded-md bg-slate-100 px-2.5 py-2 text-sm font-bold text-slate-700">
                                <span>
                                  Deadline #{pendingClose.deadline_block}
                                </span>
                                <Button
                                  size="sm"
                                  type="button"
                                  variant="secondary"
                                  disabled={isLoading || !canFinalize}
                                  onClick={() => handleFinalizeClose(fundingId)}
                                >
                                  <CheckCircle2 className="size-4" />
                                  Finalize
                                </Button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-dashed border-slate-300 px-3 py-3 text-sm font-bold text-slate-500">
                  Blockchain status unavailable.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {activeDialog === "propose" && (
        <Modal title="Propose update" onClose={() => setActiveDialog(null)}>
          <form onSubmit={handleProposeUpdate}>
            <div className="grid gap-3 p-4">
              <Field htmlFor="update-channel" label="Channel">
                <Input
                  id="update-channel"
                  readOnly
                  title={updateForm.fundingId}
                  value={shortId(updateForm.fundingId)}
                />
              </Field>
              <Field htmlFor="update-own-amount" label="New local balance">
                <Input
                  id="update-own-amount"
                  inputMode="numeric"
                  min="0"
                  type="number"
                  value={updateForm.ownAmount}
                  onChange={(event) =>
                    setUpdateForm((current) => ({
                      ...current,
                      ownAmount: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field htmlFor="update-peer-amount" label="New remote balance">
                <Input
                  id="update-peer-amount"
                  inputMode="numeric"
                  min="0"
                  type="number"
                  value={updateForm.peerAmount}
                  onChange={(event) =>
                    setUpdateForm((current) => ({
                      ...current,
                      peerAmount: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field htmlFor="update-peer-url" label="Peer URL">
                <Input
                  id="update-peer-url"
                  list={peerUrlInputListId}
                  value={updateForm.peerUrl}
                  onChange={(event) =>
                    setUpdateForm((current) => ({
                      ...current,
                      peerUrl: event.target.value,
                    }))
                  }
                  placeholder="http://127.0.0.1:8002"
                />
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-200 p-4 max-sm:grid max-sm:grid-cols-1">
              <Button
                type="button"
                variant="outline"
                onClick={() => setActiveDialog(null)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading || !updateForm.fundingId}>
                <Send className="size-4" />
                Send proposal
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {activeDialog === "accept" && (
        <Modal title="Accept update" onClose={() => setActiveDialog(null)}>
          <form onSubmit={handleAcceptUpdate}>
            <div className="grid gap-3 p-4">
              <p className="text-sm font-bold leading-6 text-slate-600">
                Confirm the pending update for channel{" "}
                <span className="text-slate-950" title={acceptForm.fundingId}>
                  {shortId(acceptForm.fundingId)}
                </span>
                .
              </p>
              <Field htmlFor="accept-proposer-url" label="Proposer URL">
                <Input
                  id="accept-proposer-url"
                  list={peerUrlInputListId}
                  value={acceptForm.proposerUrl}
                  onChange={(event) =>
                    setAcceptForm((current) => ({
                      ...current,
                      proposerUrl: event.target.value,
                    }))
                  }
                  placeholder="http://127.0.0.1:8001"
                />
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-200 p-4 max-sm:grid max-sm:grid-cols-1">
              <Button
                type="button"
                variant="outline"
                onClick={() => setActiveDialog(null)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading || !acceptForm.fundingId}>
                <Check className="size-4" />
                Confirm
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {activeDialog === "acceptFunding" && (
        <Modal title="Accept funding" onClose={() => setActiveDialog(null)}>
          <form onSubmit={handleAcceptFunding}>
            <div className="grid gap-3 p-4">
              <p className="text-sm font-bold leading-6 text-slate-600">
                Confirm the funding proposal{" "}
                <span className="text-slate-950" title={acceptFundingForm.fundingId}>
                  {shortId(acceptFundingForm.fundingId)}
                </span>
                .
              </p>
              <Field htmlFor="accept-funding-proposer-url" label="Proposer URL">
                <Input
                  id="accept-funding-proposer-url"
                  list={peerUrlInputListId}
                  value={acceptFundingForm.proposerUrl}
                  onChange={(event) =>
                    setAcceptFundingForm((current) => ({
                      ...current,
                      proposerUrl: event.target.value,
                    }))
                  }
                  placeholder="http://127.0.0.1:8001"
                />
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-200 p-4 max-sm:grid max-sm:grid-cols-1">
              <Button
                type="button"
                variant="outline"
                onClick={() => setActiveDialog(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  isLoading ||
                  !acceptFundingForm.fundingId ||
                  !normalizeUrl(acceptFundingForm.proposerUrl)
                }
              >
                <Check className="size-4" />
                Confirm
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </main>
  );
}

export default App;
