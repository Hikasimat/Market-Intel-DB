import React, { useState, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchMarketEvents } from '../../features/marketEvents/marketEventSlice';
import { createProspect, updateProspect } from '../../features/prospects/prospectSlice';
import { X, Plus, Trash2, Building, Network, Calendar } from 'lucide-react';
import api from '../../services/api';
import { toast } from 'react-toastify';
import SearchableSelect from '../common/SearchableSelect';
import { COUNTRIES } from '../../utils/countries';
import PhoneInput from 'react-phone-number-input';
import 'react-phone-number-input/style.css';
const ProspectForm = ({ isOpen, onClose, prospect = null, highlightFields = [], onSuccess = null, readOnly = false, highlightMode = 'error' }) => {
  const hColor = highlightMode === 'success' ? 'emerald' : 'red';
  const hClass = `border-2 border-${hColor}-500 bg-${hColor}-50/30 focus:border-${hColor}-500 focus:ring-${hColor}-500 text-${hColor}-900`;
  const dispatch = useDispatch();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [verifyingEmail, setVerifyingEmail] = useState(null);
  const [instantVerificationStatus, setInstantVerificationStatus] = useState(null);
  const [contactVerificationStatuses, setContactVerificationStatuses] = useState({});
  const { user } = useSelector((state) => state.auth);
  const [parentOptions, setParentOptions] = useState([]);
  const [targetOptions, setTargetOptions] = useState([]);
  const [govEntities, setGovEntities] = useState([]);
  const { items: marketEventsList } = useSelector((state) => state.marketEvents);

  const shareholdingRef = useRef(null);
  const keyContactsRef = useRef(null);
  const wasEditingRef = useRef(false);

  const initialEmptyState = {
    company_name: '', country_head_office: '', complete_address: '',
    official_phone_number: '', official_email_address: '', official_website_url: '',
    linkedin_company_page: '', primary_industries: '',
    company_structure: 'Parent', ownership_sector: 'Private Company', operational_status: 'Active',
    parent_companies: [''], status_target: '', merger_role: '', primary_offering_type: 'Multiple',
    products: [{ name: '' }], services: [{ name: '' }], solutions: [{ name: '' }], 
    key_contacts: [{ prefix: '', contact_name: '', designation: '', official_email: '', phone_number: '', linkedin_profile: '' }],
    market_event_ids: [],
    shareholdings: [],
    merging_companies: [],
    dissolved_companies: [],
    acquiring_company: null,
    acquired_shares: ''
  };

  // Form State
  const [formData, setFormData] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`prospectsFormData_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return initialEmptyState;
  });

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`prospectsFormData_${userId}`, JSON.stringify(formData));
  }, [formData, user]);

  useEffect(() => {
    if (isOpen) {
      // Fetch all prospects for parent/target dropdowns
      api.get('/prospects/?limit=1000').then(res => {
        const options = res.data.results || res.data;
        setParentOptions(options.filter(p => p.id !== prospect?.id));
        setTargetOptions(options.filter(p => p.id !== prospect?.id));
      });
      // Fetch government entities
      api.get('/government-entities/?limit=1000').then(res => {
        setGovEntities(res.data.results || res.data);
      });
    }

    if (prospect && isOpen) {
      wasEditingRef.current = true;
      dispatch(fetchMarketEvents({}));
      setFormData({
        ...prospect,
        parent_companies: (prospect.parent_companies && prospect.parent_companies.length > 0) ? prospect.parent_companies : [''],
        status_target: prospect.status_target || '',
        merger_role: prospect.merger_role || '',
        products: (prospect.products && prospect.products.length > 0) ? prospect.products : [{ name: '' }],
        services: (prospect.services && prospect.services.length > 0) ? prospect.services : [{ name: '' }],
        solutions: (prospect.solutions && prospect.solutions.length > 0) ? prospect.solutions : [{ name: '' }],
        key_contacts: (prospect.key_contacts && prospect.key_contacts.length > 0) ? prospect.key_contacts : [{ prefix: '', contact_name: '', designation: '', official_email: '', phone_number: '', linkedin_profile: '' }],
        market_event_ids: (prospect.market_events || []).map(e => e.id),
        shareholdings: (prospect.shareholdings || []).map(sh => ({
          ...sh,
          is_self: sh.company === prospect.id
        })),
        merging_companies: prospect.merging_companies || [],
        dissolved_companies: prospect.dissolved_companies || [],
        acquiring_company: (prospect.acquiring_companies && prospect.acquiring_companies.length > 0) ? prospect.acquiring_companies[0].acquiring_prospect : null,
        acquired_shares: (prospect.acquiring_companies && prospect.acquiring_companies.length > 0) ? prospect.acquiring_companies[0].acquired_shares : ''
      });
    } else if (isOpen) {
      // Preserve form data (draft) when opening "Add New Prospect" unless we just came from editing
      dispatch(fetchMarketEvents({}));
      if (wasEditingRef.current) {
        setFormData(initialEmptyState);
        wasEditingRef.current = false;
      }
      setError(null);
    }
  }, [prospect, isOpen]);

  const handleContactVerifyEmail = async (index, email) => {
    if (!email) return;
    try {
      setVerifyingEmail(`contact-${index}`);
      const res = await api.post('/email-verifications/instant-verify/', {
        email_address: email
      });
      
      setContactVerificationStatuses(prev => ({ ...prev, [index]: res.data.verification_status }));
      
      if (res.data.verification_status === 'VALID') {
        toast.success("Contact email verified successfully!");
      } else {
        toast.warning(`Contact email is ${res.data.verification_status}. Reason: ${res.data.reason}`);
      }
    } catch (err) {
      console.error('Failed to verify contact email:', err);
      const errorMessage = err.response?.data?.error || err.response?.data?.detail || err.message || 'Unknown error occurred.';
      toast.error(`Failed to verify contact email: ${errorMessage}`);
    } finally {
      setVerifyingEmail(null);
    }
  };

  const handleVerifyEmail = async () => {
    if (!formData.official_email_address) return;
    
    try {
      setVerifyingEmail(formData.official_email_address);
      const res = await api.post('/email-verifications/instant-verify/', {
        email_address: formData.official_email_address
      });
      
      setInstantVerificationStatus(res.data.verification_status);
      
      if (res.data.verification_status === 'VALID') {
        toast.success("Email verified successfully!");
      } else {
        toast.warning(`Email is ${res.data.verification_status}. Reason: ${res.data.reason}`);
      }
    } catch (err) {
      console.error('Failed to verify email:', err);
      const errorMessage = err.response?.data?.error || err.response?.data?.detail || err.message || 'Unknown error occurred.';
      toast.error(`Failed to verify email: ${errorMessage}`);
    } finally {
      setVerifyingEmail(null);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    if (name === 'official_email_address') {
      setInstantVerificationStatus(null);
    }
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleAddParent = () => {
    setFormData(prev => ({ ...prev, parent_companies: [...prev.parent_companies, ''] }));
  };

  const handleParentChange = (index, value) => {
    const newParents = [...formData.parent_companies];
    newParents[index] = value;
    setFormData(prev => ({ ...prev, parent_companies: newParents }));
  };

  const handleRemoveParent = (index) => {
    const newParents = formData.parent_companies.filter((_, i) => i !== index);
    setFormData(prev => ({ ...prev, parent_companies: newParents }));
  };

  const handleAddOffering = (type) => {
    setFormData(prev => ({
      ...prev,
      [type]: [...prev[type], { name: '', offering_type: type.slice(0, -1).charAt(0).toUpperCase() + type.slice(1, -1) }]
    }));
  };

  const handleOfferingChange = (type, index, value) => {
    setFormData(prev => {
      const newOfferings = [...prev[type]];
      newOfferings[index] = { ...newOfferings[index], name: value };
      return { ...prev, [type]: newOfferings };
    });
  };

  const handleRemoveOffering = (type, index) => {
    const newOfferings = formData[type].filter((_, i) => i !== index);
    setFormData(prev => ({ ...prev, [type]: newOfferings }));
  };

  const handleAddContact = () => {
    setFormData(prev => ({
      ...prev,
      key_contacts: [...prev.key_contacts, { prefix: '', contact_name: '', designation: '', official_email: '', phone_number: '', linkedin_profile: '' }]
    }));
  };

  const handleContactChange = (index, field, value) => {
    if (field === 'official_email') {
      setContactVerificationStatuses(prev => ({ ...prev, [index]: null }));
    }
    setFormData(prev => {
      const newContacts = [...prev.key_contacts];
      newContacts[index] = { ...newContacts[index], [field]: value };
      return { ...prev, key_contacts: newContacts };
    });
  };

  const handleRemoveContact = (index) => {
    const contactBeingRemoved = formData.key_contacts[index];
    const newContacts = formData.key_contacts.filter((_, i) => i !== index);
    
    // Clean up shareholdings that reference this contact
    const newShareholdings = formData.shareholdings.map(sh => {
      if (sh.holder_type === 'Individual') {
        if (contactBeingRemoved.id && sh.contact === contactBeingRemoved.id) {
          return { ...sh, contact: null };
        } else if (sh.contact_index === index) {
          return { ...sh, contact_index: null };
        } else if (sh.contact_index !== null && sh.contact_index > index) {
          return { ...sh, contact_index: sh.contact_index - 1 };
        }
      }
      return sh;
    });

    setFormData(prev => ({ ...prev, key_contacts: newContacts, shareholdings: newShareholdings }));
    setContactVerificationStatuses(prev => {
      const newStatuses = { ...prev };
      delete newStatuses[index];
      // re-index the following ones
      Object.keys(newStatuses).forEach(k => {
        const kInt = parseInt(k);
        if (kInt > index) {
          newStatuses[kInt - 1] = newStatuses[kInt];
          delete newStatuses[kInt];
        }
      });
      return newStatuses;
    });
  };

  const handleAddShareholding = () => {
    setFormData(prev => ({
      ...prev,
      shareholdings: [...prev.shareholdings, { holder_type: 'Company', company: '', contact: null, contact_index: null, share_percentage: '' }]
    }));
  };

  const handleShareholdingChange = (index, field, value) => {
    setFormData(prev => {
      const newShareholdings = [...prev.shareholdings];
      const current = { ...newShareholdings[index] };
      current[field] = value;
      if (field === 'holder_type') {
        current.company = '';
        current.contact = null;
        current.contact_index = null;
      }
      newShareholdings[index] = current;
      return { ...prev, shareholdings: newShareholdings };
    });

    if (field === 'holder_type' && value === 'Individual') {
      setTimeout(() => {
        keyContactsRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  };

  const handleRemoveShareholding = (index) => {
    const newShareholdings = formData.shareholdings.filter((_, i) => i !== index);
    setFormData(prev => ({ ...prev, shareholdings: newShareholdings }));
  };

  const validate = () => {
    if (!formData.company_name) return 'Company Name is required';
    if (!formData.country_head_office) return 'Country is required';
    if (!formData.complete_address) return 'Complete Address is required';
    if (!formData.primary_industries) return 'Primary Industries is required';
    if (!formData.ownership_sector) return 'Ownership Sector is required';
    if (!formData.company_structure) return 'Company Structure is required';
    if (!formData.operational_status) return 'Operational Status is required';
    if (!formData.primary_offering_type) return 'Primary Offering Type is required';

    if (['Branch', 'Subsidiary'].includes(formData.company_structure) && formData.parent_companies.filter(Boolean).length === 0) {
      return `At least one parent company is required for a ${formData.company_structure}`;
    }
    


    const uniqueParents = new Set(formData.parent_companies.filter(Boolean));
    if (uniqueParents.size !== formData.parent_companies.filter(Boolean).length) {
      return 'Duplicate parent companies are not allowed';
    }

    // Check Key Contacts emails
    for (let i = 0; i < formData.key_contacts.length; i++) {
      const contact = formData.key_contacts[i];
      if (contact.official_email) {
        // If editing an existing contact and email didn't change, bypass verification
        const existingContact = prospect?.key_contacts?.find(c => c.id === contact.id);
        const isUnchanged = existingContact && existingContact.official_email === contact.official_email;
        if (!isUnchanged && contactVerificationStatuses[i] !== 'VALID') {
          return `Please verify the Official Email for Key Contact: ${contact.contact_name || 'Contact ' + (i + 1)} before proceeding.`;
        }
      }
    }

    // Email verification check
    if (formData.official_email_address) {
      // If editing and they haven't touched the email, let it pass.
      const isUnchanged = prospect && prospect.official_email_address === formData.official_email_address;
      if (!isUnchanged && instantVerificationStatus !== 'VALID') {
        return 'Please verify the Official Email Address before proceeding. Only VALID emails are allowed.';
      }
    }

    // Shareholding validation
    for (let i = 0; i < formData.shareholdings.length; i++) {
      const sh = formData.shareholdings[i];
      if (!sh.share_percentage || isNaN(sh.share_percentage) || Number(sh.share_percentage) <= 0 || Number(sh.share_percentage) > 100) {
        return `Shares (%) must be a valid number between 0 and 100 for Shareholder ${i + 1}`;
      }
      if (sh.holder_type === 'Company' && !sh.company) {
        return `Please select a Company for Shareholder ${i + 1}`;
      }
      if (sh.holder_type === 'Individual' && !sh.contact && sh.contact_index === null) {
        return `Please select a Key Contact for Shareholder ${i + 1}`;
      }
    }

    return null;
  };

  
  const handleMarketEventToggle = (eventId) => {
    setFormData(prev => {
      const currentIds = prev.market_event_ids || [];
      const isSelected = currentIds.includes(eventId);
      return {
        ...prev,
        market_event_ids: isSelected 
          ? currentIds.filter(id => id !== eventId)
          : [...currentIds, eventId]
      };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      toast.error(validationError);
      return;
    }

    setLoading(true);
    setError(null);

    try {
            const ensureUrl = (url) => {
        if (!url || url.trim() === '') return '';
        if (!/^https?:\/\//i.test(url)) return 'https://' + url;
        return url;
      };

      const cleanData = { ...formData };
      cleanData.official_website_url = ensureUrl(cleanData.official_website_url);
      cleanData.linkedin_company_page = ensureUrl(cleanData.linkedin_company_page);
      cleanData.key_contacts = cleanData.key_contacts.map(c => ({
        ...c,
        linkedin_profile: ensureUrl(c.linkedin_profile)
      }));
      
      // Clean parents
      cleanData.parent_companies = cleanData.parent_companies.filter(Boolean);
      
      // Clean target
      if (!['Acquired', 'Merged'].includes(cleanData.operational_status)) {
        cleanData.status_target = null;
      }
      if (cleanData.status_target === '') cleanData.status_target = null;

      if (cleanData.operational_status !== 'Merged') {
        cleanData.merging_companies = [];
        cleanData.dissolved_companies = [];
      }

      if (cleanData.operational_status !== 'Acquired') {
        cleanData.acquiring_companies_data = [];
      } else {
        const shares = cleanData.acquired_shares !== '' && cleanData.acquired_shares !== null ? parseFloat(cleanData.acquired_shares) : null;
        if (cleanData.acquiring_company) {
            cleanData.acquiring_companies_data = [{
                acquiring_company: cleanData.acquiring_company,
                acquired_shares: shares
            }];
        } else {
            cleanData.acquiring_companies_data = [];
        }
      }
      delete cleanData.acquiring_company;
      delete cleanData.acquired_shares;

      // Clean offerings
      const offerings = [];
      if (['Products', 'Multiple'].includes(cleanData.primary_offering_type)) {
        offerings.push(...cleanData.products.filter(p => p.name.trim() !== '').map(p => ({ ...p, offering_type: 'Product' })));
      }
      if (['Services', 'Multiple'].includes(cleanData.primary_offering_type)) {
        offerings.push(...cleanData.services.filter(p => p.name.trim() !== '').map(p => ({ ...p, offering_type: 'Service' })));
      }
      if (['Solutions', 'Multiple'].includes(cleanData.primary_offering_type)) {
        offerings.push(...cleanData.solutions.filter(p => p.name.trim() !== '').map(p => ({ ...p, offering_type: 'Solution' })));
      }
      cleanData.offerings_data = offerings;

      // Clean contacts
      const validContacts = [];
      const oldIndexToNewIndex = {};
      cleanData.key_contacts.forEach((c, index) => {
        if (c.contact_name.trim() !== '') {
          oldIndexToNewIndex[index] = validContacts.length;
          validContacts.push(c);
        }
      });
      cleanData.key_contacts = validContacts;
      
      // Update shareholdings contact_index if any key contacts were removed
      cleanData.shareholdings = cleanData.shareholdings.map(sh => {
        let newSh = { ...sh };
        if (newSh.company === "") newSh.company = null;
        if (newSh.contact === "") newSh.contact = null;

        if (newSh.holder_type === 'Company') {
          if (newSh.company === 'self' || newSh.is_self) {
            newSh.is_self = true;
            newSh.company = null;
          } else {
            newSh.is_self = false;
          }
        }

        if (newSh.holder_type === 'Individual' && newSh.contact_index !== null && newSh.contact_index !== undefined) {
          return { ...newSh, contact_index: oldIndexToNewIndex[newSh.contact_index] !== undefined ? oldIndexToNewIndex[newSh.contact_index] : null };
        }
        return newSh;
      });
      if (prospect) {
        await dispatch(updateProspect({ id: prospect.id, data: cleanData })).unwrap();
      } else {
        await dispatch(createProspect(cleanData)).unwrap();
        setFormData(initialEmptyState);
      }
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      let errorMessage = 'An error occurred while saving.';
      
      const formatDrfError = (obj, parentKey = '') => {
        let msgs = [];
        for (const [key, value] of Object.entries(obj)) {
          const readableKey = key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
          const fullKey = parentKey ? `${parentKey} -> ${readableKey}` : readableKey;
          
          if (Array.isArray(value)) {
            msgs.push(`${fullKey}: ${value.join(' ')}`);
          } else if (typeof value === 'object' && value !== null) {
            msgs = msgs.concat(formatDrfError(value, fullKey));
          } else {
            msgs.push(`${fullKey}: ${value}`);
          }
        }
        return msgs;
      };

      if (err && typeof err === 'object' && !err.message) {
        if (err.detail) {
          errorMessage = err.detail;
        } else {
          const errors = formatDrfError(err);
          errorMessage = errors.join(' | ');
        }
      } else if (typeof err === 'string') {
        errorMessage = err;
      } else if (err && err.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex items-center justify-center p-4 sm:p-6 bg-slate-900/50 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl max-h-full bg-white shadow-xl flex flex-col rounded-2xl animate-in fade-in zoom-in-95 duration-300">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-xl font-semibold text-slate-800">
            {prospect ? 'Edit Prospect Master Data' : 'Add New Prospect'}
          </h2>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-100 transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-slate-50/50">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
              {error}
            </div>
          )}
          <fieldset disabled={readOnly} className="space-y-8">

          {/* Section 1: Corporate Structure */}
          <div className="bg-slate-50/70 rounded-xl border border-slate-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600">
                  <Network size={20} />
                </div>
                <h3 className="text-lg font-medium text-slate-800">Corporate Structure & Parent Auto-Linking</h3>
              </div>
              <span className="px-2.5 py-1 text-xs font-medium bg-indigo-50 text-indigo-700 rounded-xl border border-indigo-100">
                Feeds Relationship Visualizer
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-2">COMPANY STRUCTURE *</label>
                <SearchableSelect 
                  value={formData.company_structure} 
                  onChange={(val) => setFormData(prev => ({...prev, company_structure: val}))}
                  options={[
                    { value: 'Parent', label: 'Parent Organization (Ultimate Holding / HQ)' },
                    { value: 'Branch', label: 'Branch Office (Local Operational Branch)' },
                    { value: 'Subsidiary', label: 'Subsidiary Company (Owned Subsidiary / JV)' }
                  ]}
                />
              </div>
              
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-2">OPERATIONAL STATUS *</label>
                <SearchableSelect 
                  value={formData.operational_status} 
                  onChange={(val) => setFormData(prev => ({...prev, operational_status: val}))}
                  options={[
                    { value: 'Active', label: 'Active' },
                    { value: 'Inactive', label: 'Inactive' },
                    { value: 'Permanently Closed', label: 'Permanently Closed' },
                    { value: 'Acquired', label: 'Acquired' },
                    { value: 'Merged', label: 'Merged' }
                  ]}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-2">COMPANY TYPE *</label>
                <SearchableSelect 
                  value={formData.ownership_sector} 
                  onChange={(val) => setFormData(prev => ({...prev, ownership_sector: val}))}
                  options={[
                    { value: 'Private Company', label: 'Private Company' },
                    { value: 'Government Company', label: 'Government Company' },
                    { value: 'Semi Government Company', label: 'Semi Government Company' }
                  ]}
                />
              </div>
            </div>

            {formData.operational_status === 'Merged' && (
              <div className="mt-6 pt-6 border-t border-slate-100">
                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">MERGING COMPANIES *</label>
                    <SearchableSelect 
                      isMulti={true}
                      value={formData.merging_companies}
                      onChange={(val) => {
                        const newMerging = val || [];
                        setFormData(prev => ({
                          ...prev, 
                          merging_companies: newMerging,
                          dissolved_companies: prev.dissolved_companies.filter(d => newMerging.includes(d))
                        }));
                      }}
                      placeholder="Select all merging companies..."
                      options={parentOptions.map(opt => ({ value: opt.id, label: `${opt.company_name} (${opt.country_head_office})` }))}
                    />
                  </div>
                  
                  {formData.merging_companies.length > 0 && (
                    <div>
                      <label className="block text-sm font-bold text-slate-700 mb-1.5">DISSOLVED COMPANIES (SET TO INACTIVE)</label>
                      <p className="text-xs text-slate-500 mb-2">Select companies that will be dissolved (marked as Inactive) due to this merger.</p>
                      <SearchableSelect 
                        isMulti={true}
                        value={formData.dissolved_companies}
                        onChange={(val) => setFormData(prev => ({...prev, dissolved_companies: val || []}))}
                        placeholder="Select dissolved companies..."
                        options={parentOptions.filter(opt => formData.merging_companies.includes(opt.id)).map(opt => ({ value: opt.id, label: `${opt.company_name} (${opt.country_head_office})` }))}
                      />
                    </div>
                  )}
                </div>
              </div>
            )}

            {formData.operational_status === 'Acquired' && (
              <div className="mt-6 pt-6 border-t border-slate-100">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">ACQUIRING COMPANY *</label>
                    <SearchableSelect 
                      value={formData.acquiring_company}
                      onChange={(val) => setFormData(prev => ({...prev, acquiring_company: val}))}
                      placeholder="Select acquiring company..."
                      options={parentOptions.map(opt => ({ value: opt.id, label: `${opt.company_name} (${opt.country_head_office})` }))}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">ACQUIRED SHARES (%) *</label>
                    <input 
                      type="number" 
                      step="0.01"
                      min="0"
                      max="100"
                      value={formData.acquired_shares} 
                      onChange={(e) => setFormData(prev => ({...prev, acquired_shares: e.target.value}))} 
                      className="w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-2.5 text-slate-900 transition-all outline-none shadow-sm"
                      placeholder="e.g. 100"
                    />
                  </div>
                </div>
              </div>
            )}

            {['Branch', 'Subsidiary'].includes(formData.company_structure) && (
              <div className="mt-6 pt-6 border-t border-slate-100">
                <div className="flex justify-between items-center mb-4">
                  <label className="block text-sm font-bold text-slate-700 mb-1.5">PARENT COMPANY (ONE OR MORE SUPPORTED) *</label>
                  <button type="button" onClick={handleAddParent} className="text-sm text-indigo-600 font-medium hover:text-indigo-700 flex items-center gap-1">
                    <Plus size={16} /> Add Parent
                  </button>
                </div>
                {formData.parent_companies.map((parent, index) => (
                  <div key={index} className="flex gap-2 mb-3">
                    <div className="flex-1"><SearchableSelect 
                      value={parent}
                      onChange={(val) => handleParentChange(index, val)}
                      placeholder="Select a parent company..."
                      options={parentOptions.map(opt => ({ value: opt.id, label: `${opt.company_name} (${opt.country_head_office})` }))}
                    /></div>
                    <button type="button" onClick={() => handleRemoveParent(index)} className="p-2 text-slate-400 hover:text-red-500">
                      <Trash2 size={18} />
                    </button>
                  </div>
                ))}
                {formData.parent_companies.length === 0 && (
                  <div className="text-sm text-amber-600 bg-amber-50 p-3 rounded-xl border border-amber-100">Please add at least one parent company.</div>
                )}
              </div>
            )}

          </div>

          {/* Section 2: General Information */}
          <div className="bg-slate-50/70 rounded-xl border border-slate-200 shadow-sm p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600">
                <Building size={20} />
              </div>
              <h3 className="text-lg font-medium text-slate-800">General Information</h3>
            </div>
            
            <div className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">Company Name *</label>
                  <input type="text" name="company_name" value={formData.company_name} onChange={handleChange} className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all ${highlightFields?.includes('company_name') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`} />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">Country (Head Office) *</label>
                  <div className={`${highlightFields?.includes('country_head_office') ? hClass : ''}`}>
                    <SearchableSelect
                      options={COUNTRIES}
                      value={formData.country_head_office}
                      onChange={(value) => setFormData({ ...formData, country_head_office: value })}
                      placeholder="Select country"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">Complete Address *</label>
                <textarea name="complete_address" rows="2" value={formData.complete_address} onChange={handleChange} className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all ${highlightFields?.includes('complete_address') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`}></textarea>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">Official Phone Number</label>
                  <PhoneInput
                    defaultCountry="US"
                    international
                    value={formData.official_phone_number}
                    onChange={(val) => setFormData(prev => ({ ...prev, official_phone_number: val || '' }))}
                    className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all flex items-center ${highlightFields?.includes('official_phone_number') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:within:ring-2 focus-within:ring-indigo-100'}`}
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">Official Email Address</label>
                    {user?.role === 'PRE' && formData.official_email_address && (
                      <div className="flex items-center gap-2">
                        {instantVerificationStatus ? (
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            instantVerificationStatus === 'VALID' ? 'bg-emerald-100 text-emerald-700' :
                            instantVerificationStatus === 'INVALID' ? 'bg-red-100 text-red-700' :
                            'bg-slate-100 text-slate-700'
                          }`}>
                            {instantVerificationStatus}
                          </span>
                        ) : prospect?.company_email_verification_status && formData.official_email_address === prospect.official_email_address ? (
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            prospect.company_email_verification_status === 'VALID' ? 'bg-emerald-100 text-emerald-700' :
                            prospect.company_email_verification_status === 'INVALID' ? 'bg-red-100 text-red-700' :
                            'bg-slate-100 text-slate-700'
                          }`}>
                            {prospect.company_email_verification_status}
                          </span>
                        ) : null}
                        
                        {(!instantVerificationStatus || instantVerificationStatus !== 'VALID') && !(prospect?.company_email_verification_status === 'VALID' && formData.official_email_address === prospect.official_email_address) && (
                          <button
                            type="button"
                            onClick={handleVerifyEmail}
                            disabled={verifyingEmail === formData.official_email_address || !formData.official_email_address}
                            className="text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50 border border-indigo-200 bg-indigo-50 px-2 py-0.5 rounded"
                          >
                            {verifyingEmail === formData.official_email_address ? 'Verifying...' : 'Check Email'}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <input type="email" name="official_email_address" value={formData.official_email_address} onChange={handleChange} className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all ${highlightFields?.includes('official_email_address') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`} />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">Official Website URL</label>
                  <input type="url" name="official_website_url" value={formData.official_website_url} onChange={handleChange} className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all ${highlightFields?.includes('official_website_url') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`} />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">LinkedIn Company Page</label>
                  <input type="url" name="linkedin_company_page" value={formData.linkedin_company_page} onChange={handleChange} className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all ${highlightFields?.includes('linkedin_company_page') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`} />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-1">Primary Industries *</label>
                  <input type="text" name="primary_industries" value={formData.primary_industries} onChange={handleChange} className={`w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all ${highlightFields?.includes('primary_industries') ? hClass : 'border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'}`} />
                </div>
              </div>
            </div>
          </div>

          {/* Section: Shareholding / Ownership */}
          <div ref={shareholdingRef} className="bg-slate-50/70 rounded-xl border border-slate-200 shadow-sm p-6">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h3 className="text-lg font-medium text-slate-800">Shareholding / Ownership</h3>
              </div>
              {!readOnly && (
                <button type="button" onClick={handleAddShareholding} className="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-sm font-medium hover:bg-indigo-100 flex items-center gap-1">
                  <Plus size={16} /> Add Shareholder
                </button>
              )}
            </div>

            <div className="space-y-4">
              {formData.shareholdings.map((sh, index) => (
                <div key={index} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 relative">
                  {!readOnly && (
                    <button type="button" onClick={() => handleRemoveShareholding(index)} className="absolute top-4 right-4 text-slate-400 hover:text-red-500">
                      <Trash2 size={18} />
                    </button>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mr-8">
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Holder Type *</label>
                      <SearchableSelect 
                        value={sh.holder_type} 
                        onChange={(val) => handleShareholdingChange(index, 'holder_type', val)}
                        options={[
                          { value: 'Company', label: 'Company' },
                          { value: 'Individual', label: 'Individual' },
                          { value: 'Government', label: 'Country or State' },
                          { value: 'Other', label: 'Others' }
                        ]}
                      />
                    </div>
                    <div>
                      {sh.holder_type === 'Company' ? (
                        <>
                          <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Company *</label>
                          <SearchableSelect 
                            value={sh.is_self ? 'self' : (sh.company || '')}
                            onChange={(val) => {
                              if (val === 'self') {
                                handleShareholdingChange(index, 'is_self', true);
                                handleShareholdingChange(index, 'company', 'self');
                              } else {
                                handleShareholdingChange(index, 'is_self', false);
                                handleShareholdingChange(index, 'company', val);
                              }
                            }}
                            placeholder="Select Company..."
                            options={[
                              ...(formData.company_name ? [{ value: 'self', label: `${formData.company_name} (Self / Treasury)` }] : []),
                              ...parentOptions.map(opt => ({ value: opt.id, label: `${opt.company_name} (${opt.country_head_office})` }))
                            ]}
                          />
                        </>
                      ) : sh.holder_type === 'Government' ? (
                        <>
                          <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Government Entity Name *</label>
                          <SearchableSelect 
                            value={sh.government_entity || ''}
                            onChange={(val) => handleShareholdingChange(index, 'government_entity', val)}
                            placeholder="Select Government Entity..."
                            options={govEntities.map(opt => ({ value: opt.id, label: `${opt.name} (${opt.country})` }))}
                          />
                        </>
                      ) : sh.holder_type === 'Other' ? (
                        <>
                          <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Stakeholder Name *</label>
                          <input 
                            type="text" 
                            className="w-full rounded-xl shadow-sm text-sm px-4 py-2 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                            value={sh.other_name || ''} 
                            onChange={(e) => handleShareholdingChange(index, 'other_name', e.target.value)}
                            placeholder="Enter Name..."
                          />
                        </>
                      ) : (
                        <>
                          <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Key Contact *</label>
                          <SearchableSelect 
                            value={sh.contact ? `id:${sh.contact}` : (sh.contact_index !== null && sh.contact_index !== undefined ? `idx:${sh.contact_index}` : '')}
                            onChange={(val) => {
                              if (!val) {
                                handleShareholdingChange(index, 'contact', null);
                                handleShareholdingChange(index, 'contact_index', null);
                                return;
                              }
                              if (val.startsWith('id:')) {
                                handleShareholdingChange(index, 'contact', val.substring(3));
                                handleShareholdingChange(index, 'contact_index', null);
                              } else if (val.startsWith('idx:')) {
                                handleShareholdingChange(index, 'contact', null);
                                handleShareholdingChange(index, 'contact_index', parseInt(val.substring(4), 10));
                              }
                            }}
                            placeholder="Select Key Contact..."
                            options={formData.key_contacts.map((c, i) => {
                              const idVal = c.id ? `id:${c.id}` : `idx:${i}`;
                              const display = c.contact_name ? `${c.contact_name}${c.designation ? ` — ${c.designation}` : ''}` : `Contact ${i + 1} (Name pending)`;
                              return { value: idVal, label: display };
                            })}
                          />
                          {sh.holder_type === 'Individual' && (sh.contact || sh.contact_index !== null) && (
                            <div className="mt-2 text-sm text-slate-600 font-medium bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                              Individual Name: {sh.contact ? formData.key_contacts.find(c => c.id === sh.contact)?.contact_name : (sh.contact_index !== null ? formData.key_contacts[sh.contact_index]?.contact_name : '')}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Shares (%) *</label>
                      <input 
                        type="number" 
                        step="0.01"
                        min="0"
                        max="100"
                        value={sh.share_percentage} 
                        onChange={(e) => handleShareholdingChange(index, 'share_percentage', e.target.value)} 
                        className="w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-2.5 text-slate-900 transition-all outline-none shadow-sm"
                        disabled={readOnly}
                      />
                    </div>
                  </div>
                </div>
              ))}
              {formData.shareholdings.length === 0 && (
                <div className="text-center py-6 text-slate-500 text-sm border border-dashed border-slate-200 rounded-xl">
                  No shareholders added yet.
                </div>
              )}
            </div>
          </div>

          {/* Section 3: Market Offerings */}
          <div className="bg-slate-50/70 rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="text-lg font-medium text-slate-800 mb-4">Market Offerings</h3>
            
            <div className="mb-6">
              <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-3">Primary Offering Type</label>
              <div className="flex flex-wrap gap-3">
                {['Products', 'Services', 'Solutions', 'Multiple'].map(type => (
                  <button 
                    key={type} 
                    type="button" 
                    onClick={() => setFormData(prev => ({...prev, primary_offering_type: type}))}
                    className={`px-5 py-2.5 rounded-md text-sm font-bold transition-colors border ${
                      formData.primary_offering_type === type 
                        ? 'bg-indigo-600 border-indigo-600 text-white shadow-md shadow-indigo-500/30' 
                        : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-6 border-t border-slate-100 pt-6">
              {['Products', 'Multiple'].includes(formData.primary_offering_type) && (
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">PRODUCTS OFFERED</label>
                    <button type="button" onClick={() => handleAddOffering('products')} className="text-sm text-indigo-600 hover:text-indigo-700 flex items-center gap-1 font-medium">
                      <Plus size={16} /> Add Products Offer
                    </button>
                  </div>
                  {formData.products.map((item, index) => (
                    <div key={index} className="flex gap-2 mb-2">
                      <input type="text" value={item.name} onChange={(e) => handleOfferingChange('products', index, e.target.value)} placeholder="e.g. Enterprise Cloud Servers" className="flex-1 rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                      <button type="button" onClick={() => handleRemoveOffering('products', index)} className="p-2 text-slate-400 hover:text-red-500"><Trash2 size={18} /></button>
                    </div>
                  ))}
                </div>
              )}

              {['Services', 'Multiple'].includes(formData.primary_offering_type) && (
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">SERVICES PROVIDED</label>
                    <button type="button" onClick={() => handleAddOffering('services')} className="text-sm text-indigo-600 hover:text-indigo-700 flex items-center gap-1 font-medium">
                      <Plus size={16} /> Add Services Provide
                    </button>
                  </div>
                  {formData.services.map((item, index) => (
                    <div key={index} className="flex gap-2 mb-2">
                      <input type="text" value={item.name} onChange={(e) => handleOfferingChange('services', index, e.target.value)} placeholder="e.g. IT Strategy & Consulting" className="flex-1 rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                      <button type="button" onClick={() => handleRemoveOffering('services', index)} className="p-2 text-slate-400 hover:text-red-500"><Trash2 size={18} /></button>
                    </div>
                  ))}
                </div>
              )}

              {['Solutions', 'Multiple'].includes(formData.primary_offering_type) && (
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">SOLUTIONS PROVIDED</label>
                    <button type="button" onClick={() => handleAddOffering('solutions')} className="text-sm text-indigo-600 hover:text-indigo-700 flex items-center gap-1 font-medium">
                      <Plus size={16} /> Add Solutions Provide
                    </button>
                  </div>
                  {formData.solutions.map((item, index) => (
                    <div key={index} className="flex gap-2 mb-2">
                      <input type="text" value={item.name} onChange={(e) => handleOfferingChange('solutions', index, e.target.value)} placeholder="e.g. Digital Transformation Package" className="flex-1 rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                      <button type="button" onClick={() => handleRemoveOffering('solutions', index)} className="p-2 text-slate-400 hover:text-red-500"><Trash2 size={18} /></button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          
          {/* Section 4: Market Events */}
          <div className="bg-slate-50/70 rounded-xl border border-slate-200 shadow-sm p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600 font-bold">
                <Calendar size={20} />
              </div>
              <h3 className="text-lg font-medium text-slate-800">Market Events</h3>
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1.5 mb-3">
                Associate Market Events
              </label>
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2 mb-3">
                  {formData.market_event_ids && formData.market_event_ids.map(id => {
                    const event = marketEventsList?.find(e => e.id === id);
                    if (!event) return null;
                    return (
                      <div key={id} className="inline-flex items-center gap-2 px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-xl text-sm font-medium border border-indigo-100">
                        {event.event_title}
                        <button 
                          type="button" 
                          onClick={() => handleMarketEventToggle(id)}
                          className="hover:text-indigo-900 transition-colors ml-1 font-bold"
                        >
                          &times;
                        </button>
                      </div>
                    );
                  })}
                </div>
                
                <SearchableSelect 
                  value=""
                  onChange={(val) => {
                    if(val) handleMarketEventToggle(val);
                  }}
                  placeholder="+ Select an event to add..."
                  options={(!marketEventsList || marketEventsList.length === 0) ? [{ value: 'none', label: 'No events created yet' }] : marketEventsList.filter(e => !(formData.market_event_ids || []).includes(e.id)).map(e => ({ value: e.id, label: `${e.event_title} (${e.host_country})` }))}
                />
              </div>
            </div>
          </div>

          {/* Section 5: Key Contacts */}
          <div ref={keyContactsRef} className="bg-slate-50/70 rounded-xl border border-slate-200 shadow-sm p-6">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h3 className="text-lg font-medium text-slate-800">Key Contacts / Personnel</h3>
                <p className="text-sm text-slate-500 mt-1">Assign decision makers for this prospect</p>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => shareholdingRef.current?.scrollIntoView({ behavior: 'smooth' })} className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200 flex items-center gap-1 transition-colors">
                  Return to Shareholding
                </button>
                <button type="button" onClick={handleAddContact} className="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-sm font-medium hover:bg-indigo-100 flex items-center gap-1">
                  <Plus size={16} /> Add Key Contact
                </button>
              </div>
            </div>

            <div className="space-y-4">
              {formData.key_contacts.map((contact, index) => (
                <div key={index} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 relative">
                  <button type="button" onClick={() => handleRemoveContact(index)} className="absolute top-4 right-4 text-slate-400 hover:text-red-500">
                    <Trash2 size={18} />
                  </button>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mr-8">
                    <div className="col-span-2 md:col-span-1">
                      <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Contact Name</label>
                      <div className="flex gap-2">
                        <div className="w-40 flex-shrink-0">
                          <SearchableSelect
                            value={contact.prefix || ''}
                            onChange={(val) => handleContactChange(index, 'prefix', val)}
                            placeholder="Prefix"
                            options={[
                              { value: 'Mr.', label: 'Mr.' },
                              { value: 'Ms.', label: 'Ms.' },
                              { value: 'Mrs.', label: 'Mrs.' },
                              { value: 'Dr.', label: 'Dr.' },
                              { value: 'Prof.', label: 'Prof.' },
                              { value: 'Sir', label: 'Sir' },
                              { value: 'Madam', label: 'Madam' },
                              { value: 'His Highness', label: 'His Highness' },
                              { value: 'Her Highness', label: 'Her Highness' },
                              { value: 'His Excellency', label: 'His Excellency' },
                              { value: 'Her Excellency', label: 'Her Excellency' },
                              { value: 'Honorable', label: 'Honorable' }
                            ]}
                          />
                        </div>
                        <input type="text" value={contact.contact_name} onChange={(e) => handleContactChange(index, 'contact_name', e.target.value)} placeholder="Full Name" className="w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Designation / Role</label>
                      <input type="text" value={contact.designation} onChange={(e) => handleContactChange(index, 'designation', e.target.value)} className="w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="block text-xs font-medium text-slate-500 uppercase tracking-wider">Official Email</label>
                        {user?.role === 'PRE' && contact.official_email && (
                          <div className="flex items-center gap-2">
                            {contactVerificationStatuses[index] ? (
                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                contactVerificationStatuses[index] === 'VALID' ? 'bg-emerald-100 text-emerald-700' :
                                contactVerificationStatuses[index] === 'INVALID' ? 'bg-red-100 text-red-700' :
                                'bg-slate-100 text-slate-700'
                              }`}>
                                {contactVerificationStatuses[index]}
                              </span>
                            ) : null}
                            
                            {(!contactVerificationStatuses[index] || contactVerificationStatuses[index] !== 'VALID') && !(prospect?.key_contacts?.find(c => c.id === contact.id)?.official_email === contact.official_email) && (
                              <button
                                type="button"
                                onClick={() => handleContactVerifyEmail(index, contact.official_email)}
                                disabled={verifyingEmail === `contact-${index}` || !contact.official_email}
                                className="text-[10px] font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50 border border-indigo-200 bg-indigo-50 px-2 py-0.5 rounded"
                              >
                                {verifyingEmail === `contact-${index}` ? 'Verifying...' : 'Check'}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                      <input type="email" value={contact.official_email} onChange={(e) => handleContactChange(index, 'official_email', e.target.value)} className="w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">Phone Number</label>
                      <PhoneInput
                        defaultCountry="US"
                        international
                        value={contact.phone_number}
                        onChange={(val) => handleContactChange(index, 'phone_number', val || '')}
                        className={`w-full rounded-md shadow-sm sm:text-sm px-4 py-2.5 text-slate-900 bg-white outline-none transition-colors flex items-center ${contact.latest_call_status === 'Invalid Number' ? hClass : 'border border-slate-200 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500'}`}
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">LinkedIn Profile</label>
                      <input type="url" value={contact.linkedin_profile} onChange={(e) => handleContactChange(index, 'linkedin_profile', e.target.value)} className="w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
                    </div>
                  </div>
                </div>
              ))}
              {formData.key_contacts.length === 0 && (
                <div className="text-center py-6 text-slate-500 text-sm border border-dashed border-slate-200 rounded-xl">
                  No contacts added yet.
                </div>
              )}
            </div>
            </div>
          </fieldset>
        </div>

        <div className="px-6 py-4 border-t border-slate-200 bg-white flex justify-end gap-3 sticky bottom-0">
          <button type="button" onClick={onClose} className="px-4 py-2 border border-slate-200 text-slate-700 rounded-xl hover:bg-slate-50 text-sm font-medium transition-colors">
            {readOnly ? 'Close' : 'Cancel'}
          </button>
          {!readOnly && (
            <button type="button" onClick={handleSubmit} disabled={loading} className="px-5 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium disabled:opacity-50 transition-colors shadow-sm">
              {loading ? 'Saving...' : 'Save Prospect Record'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProspectForm;



