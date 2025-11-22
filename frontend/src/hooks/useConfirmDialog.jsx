import { useState, useCallback, useRef } from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

/**
 * Hook for showing confirmation dialogs (replaces window.confirm)
 * 
 * @returns {Object} { confirmDialog, showConfirm }
 * 
 * Usage:
 * const { confirmDialog, showConfirm } = useConfirmDialog();
 * 
 * const handleDelete = async () => {
 *   const confirmed = await showConfirm({
 *     title: 'Delete Episode?',
 *     description: 'This cannot be undone.',
 *     confirmText: 'Delete',
 *     variant: 'destructive'
 *   });
 *   if (confirmed) {
 *     // proceed with deletion
 *   }
 * };
 * 
 * return (
 *   <>
 *     <Button onClick={handleDelete}>Delete</Button>
 *     {confirmDialog}
 *   </>
 * );
 */
export function useConfirmDialog() {
  const [dialogState, setDialogState] = useState({
    open: false,
    title: '',
    description: '',
    confirmText: 'Confirm',
    cancelText: 'Cancel',
    variant: 'default', // 'default' | 'destructive'
  });
  const resolveRef = useRef(null);

  const showConfirm = useCallback((options) => {
    return new Promise((resolve) => {
      resolveRef.current = resolve;
      setDialogState({
        open: true,
        title: options.title || 'Confirm',
        description: options.description || '',
        confirmText: options.confirmText || 'Confirm',
        cancelText: options.cancelText || 'Cancel',
        variant: options.variant || 'default',
      });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    setDialogState(prev => ({ ...prev, open: false }));
    if (resolveRef.current) {
      resolveRef.current(true);
      resolveRef.current = null;
    }
  }, []);

  const handleCancel = useCallback(() => {
    setDialogState(prev => ({ ...prev, open: false }));
    if (resolveRef.current) {
      resolveRef.current(false);
      resolveRef.current = null;
    }
  }, []);

  const confirmDialog = (
    <AlertDialog open={dialogState.open} onOpenChange={(open) => {
      if (!open) {
        handleCancel();
      }
    }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{dialogState.title}</AlertDialogTitle>
          {dialogState.description && (
            <AlertDialogDescription>{dialogState.description}</AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel}>
            {dialogState.cancelText}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            className={dialogState.variant === 'destructive' ? 'bg-red-600 hover:bg-red-700 focus:ring-red-600' : ''}
          >
            {dialogState.confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirmDialog, showConfirm };
}




