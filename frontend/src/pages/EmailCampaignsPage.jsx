import React from 'react';
import { useNavigate } from 'react-router-dom';
import BulkCampaignModal from '../components/email/BulkCampaignModal';

export default function EmailCampaignsPage() {
  const navigate = useNavigate();

  return (
    <div className="space-y-4 min-h-full flex-1 flex flex-col pb-2">
      <BulkCampaignModal
        isOpen={true}
        fullPage={true}
        initialTab="ai_drafts"
        onClose={() => navigate('/inbox')}
      />
    </div>
  );
}
