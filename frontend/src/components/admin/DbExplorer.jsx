import React, { useEffect, useState } from 'react';
import { useAuth } from '@/AuthContext';
import { makeApi } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';

export default function DbExplorer() {
  const { token } = useAuth();
  const api = token ? makeApi(token) : null;
  const { toast } = useToast();
  const [tables, setTables] = useState([]);
  const [activeTable, setActiveTable] = useState(null);
  const [rows, setRows] = useState([]);
  const [columns, setColumns] = useState([]);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [editRow, setEditRow] = useState(null);
  const [editBuffer, setEditBuffer] = useState({});
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  useEffect(()=>{
    if(!api) return;
    api.get('/api/admin/db/tables')
      .then(d=> setTables(d.tables||[]))
      .catch(()=>{});
  }, [token]);

  const loadTable = (tbl, newOffset=0) => {
    if(!tbl) return;
    setLoading(true); setError(null);
    if(!api) return;
    api.get(`/api/admin/db/table/${tbl}?limit=${limit}&offset=${newOffset}`)
      .then(d=> { setActiveTable(tbl); setRows(d.rows||[]); setColumns(d.columns||[]); setOffset(d.offset); setTotal(d.total); })
      .catch(e=> {
        const msg = (e && (e.detail||e.message)) || 'Load failed';
        if (e && e.status === 403) {
          setError('Admin only');
          setActiveTable(null);
          setRows([]);
          setColumns([]);
          try { toast({ title: 'Admin only', description: 'Access denied to DB Explorer.' }); } catch {}
        } else {
          setError(msg);
        }
      })
      .finally(()=> setLoading(false));
  };

  const openEdit = (row) => { setEditRow(row); setEditBuffer(row); };
  const closeEdit = () => { setEditRow(null); setEditBuffer({}); };

  const saveEdit = () => {
    if(!activeTable || !editRow) return;
    setSaving(true); setError(null);
    // compute changed fields excluding protected id
    const updates = {};
    Object.keys(editBuffer).forEach(k=> {
      if(k==='id') return;
      if(editBuffer[k] !== editRow[k]) updates[k] = editBuffer[k];
    });
    if(Object.keys(updates).length === 0) { setSaving(false); closeEdit(); return; }
    api.patch(`/api/admin/db/table/${activeTable}/${editRow.id}`, { updates })
      .then(updated=> {
        setRows(rs => rs.map(r => r.id === updated.row.id ? updated.row : r));
        closeEdit();
        try { toast({ title: 'Row saved' }); } catch {}
      })
      .catch(e=> {
        if (e && e.status === 403) {
          setError('Admin only');
          setActiveTable(null);
          try { toast({ title: 'Admin only', description: 'Access denied to DB Explorer.' }); } catch {}
        } else {
          setError((e && (e.detail||e.message)) || 'Save failed');
        }
      })
      .finally(()=> setSaving(false));
  };

  const deleteRow = (row) => {
    if(!activeTable || !row) return;
    api.del(`/api/admin/db/table/${activeTable}/${row.id}`)
      .then(()=> {
        setRows(rs => rs.filter(r => r.id !== row.id));
        setDeleteConfirm(null);
      })
      .catch(e=> {
        if (e && e.status === 403) {
          setError('Admin only');
          setActiveTable(null);
          try { toast({ title: 'Admin only', description: 'Access denied to DB Explorer.' }); } catch {}
        } else {
          setError((e && (e.detail||e.message)) || 'Delete failed');
        }
      });
  };

  const pageCount = Math.ceil(total / limit) || 1;
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="space-y-4">
      {/* DB Explorer enabled by default for admin; edits allowed */}
      <div className="flex items-center gap-2 flex-wrap">
        {tables.map(t=> (
          <button key={t} onClick={()=> loadTable(t,0)} className={`px-3 py-1 rounded text-sm border ${t===activeTable? 'bg-blue-600 text-white':'bg-white hover:bg-blue-50'}`}>{t}</button>
        ))}
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}
      {loading && <div className="text-sm">Loading...</div>}
      {activeTable && !loading && (
        <div className="border rounded bg-white shadow-sm overflow-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr className="bg-gray-100">
                {columns.map(c=> <th key={c} className="text-left px-2 py-1 font-medium">{c}</th>)}
                <th className="px-2 py-1"/> 
              </tr>
            </thead>
            <tbody>
              {rows.map(r=> (
                <tr key={r.id || JSON.stringify(r)} className="border-t hover:bg-gray-50">
                  {columns.map(c=> <td key={c} className="px-2 py-1 whitespace-nowrap max-w-[240px] truncate" title={r[c]}>{r[c]===null? 'NULL': String(r[c])}</td>)}
                  <td className="px-2 py-1 flex gap-1">
                    <button onClick={()=> openEdit(r)} className={`hover:underline text-blue-600`}>edit</button>
                    <button onClick={()=> setDeleteConfirm(r)} className={`hover:underline text-red-600`}>del</button>
                  </td>
                </tr>
              ))}
              {rows.length===0 && <tr><td colSpan={columns.length+1} className="px-2 py-4 text-center text-gray-500">No rows</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {activeTable && (
        <div className="flex items-center gap-2 text-xs">
          <button disabled={!canPrev} onClick={()=> loadTable(activeTable, Math.max(0, offset - limit))} className={`px-2 py-1 border rounded ${canPrev? 'bg-white hover:bg-gray-50':'opacity-40 cursor-not-allowed'}`}>Prev</button>
          <div>Page {Math.floor(offset/limit)+1} / {pageCount}</div>
          <button disabled={!canNext} onClick={()=> loadTable(activeTable, offset + limit)} className={`px-2 py-1 border rounded ${canNext? 'bg-white hover:bg-gray-50':'opacity-40 cursor-not-allowed'}`}>Next</button>
          <div className="ml-auto flex items-center gap-1">
            <label>Limit:</label>
            <input type="number" value={limit} onChange={e=> setLimit(Number(e.target.value)||50)} className="w-20 border px-1 py-0.5 rounded" />
            <button onClick={()=> loadTable(activeTable,0)} className={`px-2 py-1 border rounded bg-white hover:bg-gray-50`}>Apply</button>
          </div>
        </div>
      )}

      {editRow && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="px-4 py-2 border-b flex items-center justify-between">
              <div className="font-semibold text-sm">Edit Row {editRow.id}</div>
              <button onClick={closeEdit} className="text-xs text-gray-600">close</button>
            </div>
            <div className="flex-1 overflow-auto p-4 space-y-2">
              {columns.map(c=> (
                <div key={c} className="flex items-start gap-2 text-xs">
                  <label className="w-40 font-medium pt-1">{c}</label>
                  {c==='id' || c.endsWith('_at') || c.endsWith('_episode_id') ? (
                    <div className="pt-1 text-gray-500 break-all">{String(editBuffer[c])}</div>
                  ) : (
                    <textarea
                      className="flex-1 border rounded p-1 font-mono text-[11px]"
                      rows={Math.min(8, String(editBuffer[c]||'').split('\n').length)}
                      value={editBuffer[c]===null? '': String(editBuffer[c])}
                      onChange={e=> setEditBuffer(b=> ({...b, [c]: e.target.value}))}
                    />
                  )}
                </div>
              ))}
            </div>
            <div className="px-4 py-2 border-t flex gap-2 justify-end">
              <button onClick={closeEdit} className="px-3 py-1 text-xs border rounded bg-white">Cancel</button>
              <button disabled={saving} onClick={saveEdit} className={`px-3 py-1 text-xs border rounded bg-blue-600 text-white disabled:opacity-50`}>{saving? 'Saving...':'Save'}</button>
            </div>
          </div>
        </div>
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow p-4 w-full max-w-sm text-xs space-y-3">
            <div className="font-semibold">Delete Row</div>
            <div>Are you sure you want to delete id {deleteConfirm.id}? This cannot be undone.</div>
            <div className="flex justify-end gap-2">
              <button onClick={()=> setDeleteConfirm(null)} className="px-3 py-1 border rounded bg-white">Cancel</button>
              <button onClick={()=> deleteRow(deleteConfirm)} className={`px-3 py-1 border rounded bg-red-600 text-white`}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
