import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { BankProvider } from './context/BankContext';
import Layout from './components/Layout';
import OTPModal from './components/OTPModal';
import Dashboard from './pages/Dashboard';
import Transfer from './pages/Transfer';

export default function App() {
  return (
    <BrowserRouter>
      <BankProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/transfer" element={<Transfer />} />
          </Routes>
        </Layout>
        <OTPModal />
      </BankProvider>
    </BrowserRouter>
  );
}
