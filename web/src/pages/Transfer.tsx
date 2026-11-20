import { Link } from 'react-router-dom';
import TransferForm from '../components/TransferForm';

export default function Transfer() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to="/"
          className="text-gray-500 hover:text-gray-300 transition-colors text-sm"
        >
          ← Back
        </Link>
        <h1 className="text-xl font-semibold text-white">New Transfer</h1>
      </div>
      <TransferForm />
    </div>
  );
}
