import React, { useState, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { createUser, updateUser } from '../../features/users/userSlice';
import { X } from 'lucide-react';
import SearchableSelect from '../common/SearchableSelect';

const UserForm = ({ isOpen, onClose, userToEdit }) => {
  const dispatch = useDispatch();
  const { user } = useSelector(state => state.auth);
  const wasEditingRef = useRef(false);
  const initialEmptyState = {
    email: '',
    first_name: '',
    last_name: '',
    role: 'PRE',
    timezone: 'UTC',
    password: ''
  };

  const [formData, setFormData] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`userFormData_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return initialEmptyState;
  });

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`userFormData_${userId}`, JSON.stringify(formData));
  }, [formData, user]);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (isOpen) {
      if (userToEdit) {
        wasEditingRef.current = true;
        setFormData({
          email: userToEdit.email || '',
          first_name: userToEdit.first_name || '',
          last_name: userToEdit.last_name || '',
          role: userToEdit.role || 'PRE',
          timezone: userToEdit.timezone || 'UTC',
          password: '' // empty password on edit
        });
      } else {
        if (wasEditingRef.current) {
          setFormData(initialEmptyState);
          wasEditingRef.current = false;
        }
      }
    }
  }, [userToEdit, isOpen]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    try {
      if (userToEdit) {
        const data = { ...formData };
        if (!data.password) delete data.password;
        await dispatch(updateUser({ id: userToEdit.id, data })).unwrap();
      } else {
        await dispatch(createUser(formData)).unwrap();
        setFormData(initialEmptyState);
      }
      onClose();
    } catch (err) {
      setErrorMsg(typeof err === 'string' ? err : JSON.stringify(err));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 transition-opacity bg-slate-900/75 backdrop-blur-sm" onClick={onClose}></div>
        <span className="hidden sm:inline-block sm:align-middle sm:h-screen">&#8203;</span>
        <div className="relative z-10 inline-block px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transition-all transform bg-slate-50 rounded-xl shadow-xl sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6 border border-slate-200">
          <div className="flex justify-between items-center mb-5 border-b border-slate-100 pb-4">
            <h3 className="text-xl font-bold text-slate-900">{userToEdit ? 'Edit User' : 'Create New User'}</h3>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-500 transition-colors bg-slate-50 hover:bg-slate-100 rounded-full p-2">
              <X size={20} />
            </button>
          </div>
          
          <form onSubmit={handleSubmit} className="space-y-4">
            {errorMsg && (
              <div className="p-3 bg-red-50 text-red-700 rounded text-sm mb-4 border border-red-200">
                {errorMsg}
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">First Name</label>
                <input type="text" name="first_name" required value={formData.first_name} onChange={handleChange} className="mt-1 block w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Last Name</label>
                <input type="text" name="last_name" required value={formData.last_name} onChange={handleChange} className="mt-1 block w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
              </div>
            </div>
            
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1.5">Email Address (Username)</label>
              <input type="email" name="email" required value={formData.email} onChange={handleChange} className="mt-1 block w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Role</label>
                <SearchableSelect 
                  value={formData.role} 
                  onChange={(val) => setFormData(prev => ({...prev, role: val}))}
                  options={[
                    { value: 'PRE', label: 'Prospect Research Engineer (PRE)' },
                    { value: 'MANAGER', label: 'Manager' },
                    { value: 'DM', label: 'Digital Marketing' }
                  ]}
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Time Zone</label>
                <SearchableSelect 
                  value={formData.timezone} 
                  onChange={(val) => setFormData(prev => ({...prev, timezone: val}))}
                  options={[
                    { value: 'UTC', label: 'UTC' },
                    { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
                    { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
                    { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
                    { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
                    { value: 'Europe/London', label: 'London' },
                    { value: 'Europe/Paris', label: 'Paris' },
                    { value: 'Asia/Dubai', label: 'Dubai' },
                    { value: 'Asia/Kolkata', label: 'India (IST)' },
                    { value: 'Asia/Singapore', label: 'Singapore' },
                    { value: 'Australia/Sydney', label: 'Sydney' }
                  ]}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-700 mb-1.5">{userToEdit ? 'Password (leave blank to keep current)' : 'Password'}</label>
              <input type="password" name="password" required={!userToEdit} value={formData.password} onChange={handleChange} className="mt-1 block w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm" />
            </div>

            <div className="mt-5 sm:mt-6 sm:flex sm:flex-row-reverse gap-3 pt-4 border-t border-slate-100">
              <button type="submit" className="w-full inline-flex justify-center rounded-full border border-transparent shadow-md shadow-indigo-500/30 px-6 py-2.5 bg-indigo-600 text-sm font-bold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:ml-3 sm:w-auto transition-colors">
                {userToEdit ? 'Update User' : 'Create User'}
              </button>
              <button type="button" onClick={onClose} className="mt-3 w-full inline-flex justify-center rounded-xl border border-slate-200 shadow-sm px-6 py-2.5 bg-white text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:w-auto sm:text-sm transition-colors">
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default UserForm;
