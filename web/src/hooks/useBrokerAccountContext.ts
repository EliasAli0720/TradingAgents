import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { getBrokerChannel, isDesktop } from '@/api/brokerChannel';
import {
  brokerAccountOptions,
  resolveBrokerAccountKey,
  type BrokerAccountOption,
  type BrokerAccountSource,
} from '@/api/brokerAccountContext';

const STORAGE_KEY = 'tradingagents.brokerAccount.selectedKey';
const EVENT_NAME = 'tradingagents:broker-account-selected';

function readStoredSelectedKey(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

function writeStoredSelectedKey(key: string): void {
  try {
    if (key) window.localStorage.setItem(STORAGE_KEY, key);
    else window.localStorage.removeItem(STORAGE_KEY);
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: key }));
  } catch {
    /* selection persistence is best effort */
  }
}

export function useBrokerAccountContext() {
  const channel = useMemo(() => getBrokerChannel(), []);
  const desktop = isDesktop();
  const [selectedKey, setSelectedKeyState] = useState(readStoredSelectedKey);

  const serverStatus = useQuery({
    queryKey: ['broker', 'status', 'server'],
    queryFn: () => brokerApi.status(),
    enabled: channel.kind === 'server' || desktop,
    refetchInterval: 30000,
    retry: 1,
  });
  const localStatus = useQuery({
    queryKey: ['broker', 'status', 'local'],
    queryFn: () => channel.status(),
    enabled: desktop,
    refetchInterval: 5000,
    retry: 1,
  });

  const options = useMemo(
    () =>
      brokerAccountOptions({
        serverStatus: serverStatus.data,
        localStatus: localStatus.data,
        includeLocal: desktop,
      }),
    [desktop, localStatus.data, serverStatus.data],
  );

  useEffect(() => {
    if (options.length === 0) return;
    const resolved = resolveBrokerAccountKey(options, selectedKey);
    if (resolved !== selectedKey) {
      setSelectedKeyState(resolved);
      writeStoredSelectedKey(resolved);
    }
  }, [options, selectedKey]);

  useEffect(() => {
    const sync = () => setSelectedKeyState(readStoredSelectedKey());
    window.addEventListener(EVENT_NAME, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(EVENT_NAME, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setSelectedKey = useCallback((key: string) => {
    setSelectedKeyState(key);
    writeStoredSelectedKey(key);
  }, []);

  const selected = options.find((option) => option.key === selectedKey) ?? options[0] ?? null;
  const source: BrokerAccountSource | null = selected?.source ?? null;
  const account = useCallback(
    () =>
      source === 'local'
        ? channel.account(selected?.account_id)
        : brokerApi.account(
            selected?.account_id
              ? { account_id: selected.account_id, broker: selected.broker }
              : undefined,
          ),
    [channel, selected?.account_id, selected?.broker, source],
  );
  const positions = useCallback(
    () =>
      source === 'local'
        ? channel.positions(selected?.account_id)
        : brokerApi.positions(
            selected?.account_id
              ? { account_id: selected.account_id, broker: selected.broker }
              : undefined,
          ),
    [channel, selected?.account_id, selected?.broker, source],
  );
  const orders = useCallback(
    () =>
      brokerApi.orders(
        selected?.account_id
          ? { account_id: selected.account_id, broker: selected.broker }
          : undefined,
      ),
    [selected?.account_id, selected?.broker],
  );

  return {
    channel,
    options,
    selected: selected as BrokerAccountOption | null,
    selectedKey: selected?.key ?? '',
    setSelectedKey,
    isLoading: serverStatus.isLoading || (desktop && localStatus.isLoading),
    account,
    positions,
    orders,
  };
}
