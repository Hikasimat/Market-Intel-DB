import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { fetchLqPipelineItem, clearSelectedItem, reportIssueToPre, updateVerification } from '../features/lqPipeline/lqPipelineSlice';
import { 
  ArrowLeft, Building2, Globe, MapPin, Briefcase, Tag, Target, CheckCircle, XCircle, Phone, Mail, FileEdit, Clock, Network
} from 'lucide-react';
import LqWorkspaceModal from '../components/lq/LqWorkspaceModal';
import CorporateStructureTree from '../components/prospects/CorporateStructureTree';

const LqPipelineDetailPage = () => {
  const { id } = useParams();
  const dispatch = useDispatch();
  const { selectedItem: lq, loading, error } = useSelector((state) => state.lqPipeline);
  const { user } = useSelector((state) => state.auth);
  const isManager = user?.role === 'MANAGER';
  
  const [showWorkspace, setShowWorkspace] = useState(false);

  const [verificationFields, setVerificationFields] = useState({
    companyName: 'Correct',
    country: 'Correct',
    address: 'Correct',
    website: 'Correct',
    linkedIn: 'Correct',
    email: 'Correct',
    contactNo: 'Correct',
    productService: 'Correct'
  });

  const openWorkspace = (lqData) => {
    const savedChecklist = lqData.verification_checklist || {};
    setVerificationFields({
      companyName: savedChecklist.companyName || 'Correct',
      country: savedChecklist.country || 'Correct',
      address: savedChecklist.address || 'Correct',
      website: savedChecklist.website || 'Correct',
      linkedIn: savedChecklist.linkedIn || 'Correct',
      email: savedChecklist.email || 'Correct',
      contactNo: savedChecklist.contactNo || 'Correct',
      productService: savedChecklist.productService || 'Correct'
    });
    setShowWorkspace(true);
  };

  const handleFieldToggle = (key, value) => {
    setVerificationFields(prev => ({ ...prev, [key]: value }));
  };

  const incorrectFields = Object.keys(verificationFields).filter(key => verificationFields[key] === 'Incorrect');
  const allCorrect = Object.keys(verificationFields).every(key => verificationFields[key] === 'Correct');
  const hasIncorrect = incorrectFields.length > 0;

  const fieldNames = {
    companyName: 'Company Name',
    country: 'Country',
    address: 'Address',
    website: 'Website',
    linkedIn: 'LinkedIn Page',
    email: 'Official Email',
    contactNo: 'Contact No.',
    productService: 'Product, Service & Solution'
  };

  const handleSubmitIssue = () => {
    const incorrectNames = incorrectFields.map(key => fieldNames[key]);
    const autoCategory = incorrectNames.join(', ');
    const autoDetails = incorrectNames.length > 0 ? `The following fields are incorrect and need to be fixed by PRE:\n- ${incorrectNames.join('\n- ')}` : '';

    dispatch(reportIssueToPre({
      id: lq.id,
      issueData: {
        issue_category: autoCategory,
        issue_details: autoDetails,
        verification_checklist: verificationFields
      }
    }));
    setShowWorkspace(false);
  };

  const handleReadyForOutreach = () => {
    dispatch(updateVerification({ 
      id: lq.id, 
      verification_status: 'Verified',
      verification_checklist: verificationFields 
    }));
    setShowWorkspace(false);
  };

  useEffect(() => {
    dispatch(fetchLqPipelineItem(id));
    return () => {
      dispatch(clearSelectedItem());
    };
  }, [dispatch, id]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[50vh]">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
          <span className="font-medium">Loading prospect details...</span>
        </div>
      </div>
    );
  }

  if (error || !lq) {
    return (
      <div className="p-8">
        <div className="bg-red-50 text-red-600 p-4 rounded-xl flex items-center gap-2">
          <XCircle className="w-5 h-5" />
          <span className="font-semibold">{error || 'Prospect not found'}</span>
        </div>
      </div>
    );
  }

  const p = lq.prospect;
  const isLeadFreeze = lq.qualification_status === 'Lead Freeze';
  const isLeadQualified = lq.qualification_status === 'Lead Qualified';
  const isVerified = lq.verification_status === 'Verified';
  const hasIssue = lq.pre_task_status === 'ISSUE_SENT_TO_PRE';

  return (
    <div className="space-y-6">
      {/* Top Navigation */}
      <div className="flex items-center justify-between">
        <Link 
          to="/prospects?tab=pipeline" 
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-indigo-600 transition"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Pipeline
        </Link>
        {!isManager && (
          <button
            onClick={() => openWorkspace(lq)}
            disabled={isLeadFreeze}
            className={`px-4 py-2 rounded-lg font-bold text-sm shadow-sm transition flex items-center gap-2 ${
              isLeadFreeze 
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed' 
                : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200'
            }`}
          >
            {isLeadFreeze ? (
              <><XCircle className="w-4 h-4" /> Lead Freeze (Outreach Disabled)</>
            ) : (
              <><Target className="w-4 h-4" /> Open Outreach Workspace</>
            )}
          </button>
        )}
      </div>

      {/* Header Banner */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-wrap gap-6 items-start justify-between">
        <div className="flex items-center gap-5">
          <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
            <Building2 className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900">{p.company_name}</h1>
            <div className="flex items-center gap-4 text-sm text-slate-500 mt-2 font-medium">
              <span className="flex items-center gap-1.5"><MapPin className="w-4 h-4" /> {p.country_head_office}</span>
              <span className="flex items-center gap-1.5"><Briefcase className="w-4 h-4" /> {p.primary_industries}</span>
              {p.official_website_url && (
                <a href={p.official_website_url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-indigo-600 hover:underline">
                  <Globe className="w-4 h-4" /> Website
                </a>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex flex-col items-end gap-2">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Verification Status</span>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
              isVerified ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-50 text-slate-600 border-slate-200'
            }`}>
              {lq.verification_status}
            </span>
          </div>
          <div className="w-px h-10 bg-slate-200 mx-2"></div>
          <div className="flex flex-col items-end gap-2">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Qualification Status</span>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border flex items-center gap-1.5 ${
              isLeadQualified ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 
              isLeadFreeze ? 'bg-red-50 text-red-700 border-red-200' : 
              'bg-blue-50 text-blue-700 border-blue-200'
            }`}>
              {isLeadQualified && <CheckCircle className="w-3 h-3" />}
              {isLeadFreeze && <XCircle className="w-3 h-3" />}
              {lq.qualification_status}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Master Data */}
        <div className="space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
            <h3 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2">
              <Building2 className="w-4 h-4 text-slate-400" /> Company Profile
            </h3>
            <div className="space-y-4">
              <div>
                <span className="block text-xs font-semibold text-slate-400 mb-1">Structure</span>
                <span className="text-sm font-semibold text-slate-800 bg-slate-100 px-2 py-1 rounded-md">{p.company_structure}</span>
              </div>
              <div>
                <span className="block text-xs font-semibold text-slate-400 mb-1">Operational Status</span>
                <span className="text-sm font-semibold text-slate-800 bg-slate-100 px-2 py-1 rounded-md">{p.operational_status}</span>
              </div>
              <div>
                <span className="block text-xs font-semibold text-slate-400 mb-1">Address</span>
                <p className="text-sm text-slate-600 leading-relaxed">{p.complete_address || 'Not provided'}</p>
              </div>
            </div>
          </div>

          {(p.products?.length > 0 || p.services?.length > 0 || p.solutions?.length > 0) && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <h3 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2">
                <Tag className="w-4 h-4 text-slate-400" /> Offerings
              </h3>
              <div className="space-y-4">
                {p.products?.length > 0 && (
                  <div>
                    <span className="block text-xs font-bold text-slate-400 mb-2">Products</span>
                    <div className="flex flex-wrap gap-2">
                      {p.products.map(x => <span key={x.id} className="text-xs font-medium bg-indigo-50 text-indigo-700 px-2 py-1 rounded border border-indigo-100">{x.name}</span>)}
                    </div>
                  </div>
                )}
                {p.services?.length > 0 && (
                  <div>
                    <span className="block text-xs font-bold text-slate-400 mb-2">Services</span>
                    <div className="flex flex-wrap gap-2">
                      {p.services.map(x => <span key={x.id} className="text-xs font-medium bg-emerald-50 text-emerald-700 px-2 py-1 rounded border border-emerald-100">{x.name}</span>)}
                    </div>
                  </div>
                )}
                {p.solutions?.length > 0 && (
                  <div>
                    <span className="block text-xs font-bold text-slate-400 mb-2">Solutions</span>
                    <div className="flex flex-wrap gap-2">
                      {p.solutions.map(x => <span key={x.id} className="text-xs font-medium bg-amber-50 text-amber-700 px-2 py-1 rounded border border-amber-100">{x.name}</span>)}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Key Contacts */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-lg font-black text-slate-800 flex items-center gap-2">
            Key People & Call Outcomes
          </h2>
          
          {p.key_contacts?.length > 0 ? (
            <div className="space-y-3">
              {p.key_contacts.map(contact => (
                <div key={contact.id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between hover:border-indigo-200 transition">
                  <div>
                    <div className="font-bold text-slate-900 text-base">{contact.contact_name}</div>
                    <div className="text-sm text-indigo-600 font-medium mb-3">{contact.designation || 'No Designation'}</div>
                    <div className="space-y-1.5">
                      {contact.official_email && (
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <Mail className="w-3.5 h-3.5 text-slate-400" /> {contact.official_email}
                        </div>
                      )}
                      {contact.phone_number && (
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <Phone className="w-3.5 h-3.5 text-slate-400" /> {contact.phone_number}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col items-start md:items-end gap-2 min-w-[200px]">
                    <div className="w-full bg-slate-50 p-3 rounded-xl border border-slate-100">
                      <span className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Latest Outcome</span>
                      {contact.latest_communication_outcome ? (
                        <div className="flex items-center gap-1.5">
                          {contact.latest_communication_outcome === 'Lead Qualified' ? (
                            <CheckCircle className="w-4 h-4 text-emerald-500" />
                          ) : contact.latest_communication_outcome === 'Not Interested' ? (
                            <XCircle className="w-4 h-4 text-red-500" />
                          ) : (
                            <Clock className="w-4 h-4 text-blue-500" />
                          )}
                          <span className="text-sm font-bold text-slate-700">{contact.latest_communication_outcome}</span>
                        </div>
                      ) : (
                        <span className="text-sm text-slate-400 italic">No calls logged yet</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-white border-2 border-dashed border-slate-200 rounded-xl p-8 text-center">
              <p className="text-slate-500 font-medium">No Key People found for this prospect.</p>
            </div>
          )}
        </div>
      </div>

      {/* Branch Visualization Structure */}
      <div className="mt-8 mb-8">
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Network className="h-6 w-6 text-indigo-600" />
          Branch Visualization Structure
        </h2>
        <CorporateStructureTree prospect={p} />
      </div>

      {/* Workspace Modal */}
      {showWorkspace && lq && (
        <LqWorkspaceModal
          selectedLq={lq}
          initialTab={lq.verification_status === 'Verified' ? 'outreach' : 'verification'}
          onClose={() => { setShowWorkspace(false); dispatch(fetchLqPipelineItem(id)); }}
          hasIncorrect={hasIncorrect}
          allCorrect={allCorrect}
          verificationFields={verificationFields}
          handleFieldToggle={handleFieldToggle}
          handleSubmitIssue={handleSubmitIssue}
          handleReadyForOutreach={handleReadyForOutreach}
        />
      )}
    </div>
  );
};

export default LqPipelineDetailPage;
