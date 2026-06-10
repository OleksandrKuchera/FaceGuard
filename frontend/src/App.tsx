import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { ErrorBoundary } from '@/components/ErrorBoundary';

// Eager-load Login so the auth flow has no spinner on first paint
import Login from '@/pages/Login';

// All authenticated pages are lazy — split into separate chunks
const Dashboard    = lazy(() => import('@/pages/Dashboard'));
const Monitor      = lazy(() => import('@/pages/Monitor'));
const Webcam       = lazy(() => import('@/pages/Webcam'));
const Persons      = lazy(() => import('@/pages/Persons'));
const PersonDetail = lazy(() => import('@/pages/PersonDetail'));
const Cameras      = lazy(() => import('@/pages/Cameras'));
const Events       = lazy(() => import('@/pages/Events'));
const Reports      = lazy(() => import('@/pages/Reports'));
const Security     = lazy(() => import('@/pages/Security'));
const Users        = lazy(() => import('@/pages/Users'));
const Settings     = lazy(() => import('@/pages/Settings'));

function PageLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-[var(--fg-base)]">
      <div className="spinner" />
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/login"          element={<Login />} />
            <Route path="/"               element={<ProtectedRoute><ErrorBoundary><Dashboard /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/monitor"        element={<ProtectedRoute><ErrorBoundary><Monitor /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/webcam"         element={<ProtectedRoute><ErrorBoundary><Webcam /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/persons"        element={<ProtectedRoute><ErrorBoundary><Persons /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/persons/:id"    element={<ProtectedRoute><ErrorBoundary><PersonDetail /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/cameras"        element={<ProtectedRoute><ErrorBoundary><Cameras /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/events"         element={<ProtectedRoute><ErrorBoundary><Events /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/reports"        element={<ProtectedRoute><ErrorBoundary><Reports /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/security"       element={<ProtectedRoute><ErrorBoundary><Security /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/users"          element={<ProtectedRoute><ErrorBoundary><Users /></ErrorBoundary></ProtectedRoute>} />
            <Route path="/settings"       element={<ProtectedRoute><ErrorBoundary><Settings /></ErrorBoundary></ProtectedRoute>} />
            <Route path="*"               element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
