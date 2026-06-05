import { brokerApi, type BrokerOrder } from './broker';
import { getBrokerChannel } from './brokerChannel';
import { brokerNotConnectedError, isUsableBrokerStatus, shouldUseServerProposal } from './brokerReadiness';
import type { BrokerAccountSource } from './brokerAccountContext';

export async function cancelOrder(
  order: BrokerOrder,
  options?: { source?: BrokerAccountSource },
): Promise<{ cancelled: boolean }> {
  const channel = getBrokerChannel();
  const serverStatus = await brokerApi.status();

  if (options?.source !== 'local' && shouldUseServerProposal(serverStatus)) {
    return brokerApi.cancel(order.broker_order_id);
  }

  if (options?.source === 'server' || channel.kind === 'server' || !channel.cancel) {
    if (!isUsableBrokerStatus(serverStatus)) {
      throw brokerNotConnectedError();
    }
    return brokerApi.cancel(order.broker_order_id);
  }

  const localStatus = await channel.status();
  if (!isUsableBrokerStatus(localStatus)) {
    throw brokerNotConnectedError();
  }

  const result = await channel.cancel(order.broker_order_id);
  if (result.cancelled) {
    await brokerApi.updateOrderStatus(order.broker_order_id, {
      status: 'cancelled',
      filled_qty: order.filled_qty,
      filled_avg_price: order.filled_avg_price,
    });
  }
  return result;
}
