import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { toast } from 'react-toastify';
import { fetchUsers, deleteUser } from '../features/users/userSlice';
import UserForm from '../components/users/UserForm';
import { Users, Plus, Edit2, Trash2, Eye } from 'lucide-react';

const UserManagementPage = () => {
  const dispatch = useDispatch();
  const { items, loading, error } = useSelector((state) => state.users);
  const { user: currentUser } = useSelector((state) => state.auth);
  const [isFormOpen, setIsFormOpen] = useState(() => {
    const userId = currentUser?.id || 'default';
    return sessionStorage.getItem(`userFormOpen_${userId}`) === 'true';
  });
  const [editingUser, setEditingUser] = useState(() => {
    const userId = currentUser?.id || 'default';
    const saved = sessionStorage.getItem(`userEditing_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });

  useEffect(() => {
    const userId = currentUser?.id || 'default';
    sessionStorage.setItem(`userFormOpen_${userId}`, isFormOpen);
    if (editingUser) {
      sessionStorage.setItem(`userEditing_${userId}`, JSON.stringify(editingUser));
    } else {
      sessionStorage.removeItem(`userEditing_${userId}`);
    }
  }, [isFormOpen, editingUser, currentUser]);

  // Managers have full CRUD (but are restricted from modifying superusers in backend)
  const isManager = currentUser?.role === 'MANAGER' && !currentUser?.is_superuser;

  useEffect(() => {
    dispatch(fetchUsers());
  }, [dispatch]);

  const handleAddClick = () => {
    setEditingUser(null);
    setIsFormOpen(true);
  };

  const handleEditClick = (user) => {
    setEditingUser(user);
    setIsFormOpen(true);
  };

  const handleDelete = async (id) => {
    try {
      await dispatch(deleteUser(id)).unwrap();
      toast.success('User deleted successfully.');
    } catch (err) {
      toast.error('Failed to delete user.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Users className="h-6 w-6 text-indigo-600" />
            User Management
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            {isManager
              ? 'Create, edit, and manage user accounts (Manager cannot modify superusers).'
              : 'Create, edit, and manage user accounts and their roles (PRE / LQ / MANAGER).'}
          </p>
        </div>
        <div className="mt-4 sm:mt-0">
          <button
            onClick={handleAddClick}
            className="inline-flex items-center px-4 py-2 border border-transparent rounded-xl shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
          >
            <Plus className="-ml-1 mr-2 h-5 w-5" aria-hidden="true" />
            Add User
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {error && (
          <div className="p-4 bg-red-50 border-b border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">User</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Role</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Email (Username)</th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan="4" className="px-6 py-12 text-center text-slate-500">
                    <div className="flex justify-center items-center gap-2">
                      <div className="w-4 h-4 rounded-full bg-indigo-600 animate-ping"></div>
                      Loading users...
                    </div>
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan="4" className="px-6 py-12 text-center text-slate-500">
                    No users found.
                  </td>
                </tr>
              ) : (
                items.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-slate-900">
                        {user.first_name} {user.last_name}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-bold rounded text-white ${
                        user.role === 'PRE'
                          ? 'bg-indigo-600'
                          : user.role === 'MANAGER'
                          ? 'bg-amber-600'
                          : user.is_superuser
                          ? 'bg-slate-700'
                          : 'bg-emerald-600'
                      }`}>
                        {user.is_superuser ? 'ADMIN' : user.role}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600">
                      {user.email || user.username}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="flex justify-end gap-3 items-center">
                        <button onClick={() => handleEditClick(user)} className="text-indigo-600 hover:text-indigo-900" title="Edit User">
                          <Edit2 size={18} />
                        </button>
                        {currentUser?.is_superuser && (
                          <button onClick={() => handleDelete(user.id)} className="text-red-500 hover:text-red-700" title="Delete User">
                            <Trash2 size={18} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <UserForm 
        isOpen={isFormOpen} 
        onClose={() => setIsFormOpen(false)} 
        userToEdit={editingUser} 
      />
    </div>
  );
};

export default UserManagementPage;
