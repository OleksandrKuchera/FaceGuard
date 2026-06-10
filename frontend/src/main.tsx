import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <TooltipProvider>
      <App />
      <Toaster position="top-right" richColors closeButton />
    </TooltipProvider>
  </React.StrictMode>,
)
