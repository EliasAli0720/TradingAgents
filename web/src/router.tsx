import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import RequireAuth from './components/layout/RequireAuth';
import RequireRole from './components/layout/RequireRole';
import BrokerGate from './components/broker/BrokerGate';
import PortfolioPage from './routes/placeholder/portfolio';
import PerformancePage from './routes/placeholder/performance';
import TradesPage from './routes/placeholder/trades';
import RiskPage from './routes/placeholder/risk';
import BrokerStatusPage from './routes/broker/status';
import BrokerApprovalsPage from './routes/broker/approvals';
import BrokerOrdersPage from './routes/broker/orders';
import LoginPage from './routes/login';
import AnalysisListPage from './routes/analysis/list';
import AnalysisNewPage from './routes/analysis/new';
import AnalysisDetailPage from './routes/analysis/detail';
import RecommendationsPage from './routes/recommendations';
import ModelSettingsPage from './routes/settings/model';
import TranslationSettingsPage from './routes/settings/translation';
import AccountSettingsPage from './routes/settings/account';
import AdminUsersPage from './routes/admin/users';
import AdminRunsPage from './routes/admin/runs';

export const router = createBrowserRouter([
  {
    element: (
      <div className="h-full min-h-0">
        <Outlet />
      </div>
    ),
    children: [
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      { path: '/', element: <Navigate to="/analysis" replace /> },
      { path: '/recommendations', element: <RecommendationsPage /> },
      { path: '/analysis', element: <AnalysisListPage /> },
      { path: '/analysis/new', element: <AnalysisNewPage /> },
      { path: '/analysis/:runId', element: <AnalysisDetailPage /> },
      { path: '/broker', element: <BrokerGate><BrokerStatusPage /></BrokerGate> },
      { path: '/broker/approvals', element: <BrokerGate><BrokerApprovalsPage /></BrokerGate> },
      { path: '/broker/orders', element: <BrokerGate><BrokerOrdersPage /></BrokerGate> },
      { path: '/portfolio', element: <BrokerGate><PortfolioPage /></BrokerGate> },
      { path: '/performance', element: <BrokerGate><PerformancePage /></BrokerGate> },
      { path: '/trades', element: <BrokerGate><TradesPage /></BrokerGate> },
      { path: '/risk', element: <BrokerGate><RiskPage /></BrokerGate> },
      { path: '/settings/model', element: <ModelSettingsPage /> },
      { path: '/settings/translation', element: <TranslationSettingsPage /> },
      { path: '/settings/account', element: <AccountSettingsPage /> },
      {
        path: '/admin/users',
        element: <RequireRole roles={['admin']}><AdminUsersPage /></RequireRole>,
      },
      {
        path: '/admin/runs',
        element: <RequireRole roles={['admin']}><AdminRunsPage /></RequireRole>,
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
