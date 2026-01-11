'use client';

import React, { useState, useEffect } from 'react';
import {
    Plus,
    ArrowLeft,
    Upload,
    MessageSquare,
    BookOpen,
    Trash2,
    Edit3,
    FileText,
    Loader2,
    Check,
    X
} from 'lucide-react';
import {
    loadKnowledgeBases,
    createKnowledgeBase,
    loadKBChats,
    createKBChat,
    deleteKnowledgeBase,
    updateKnowledgeBase,
    loadKBDocuments,
    deleteKBDocument,
    deleteKBChat,
    updateChatTitle
} from '@/utils/api';
import { KnowledgeBase, KBChat, KBDocument } from '@/types';

interface KnowledgeBaseSidebarProps {
    onSelectChat: (kbId: string, chatId: string) => void;
    onUploadFiles: (kbId: string) => void;
}

export default function KnowledgeBaseSidebar({
    onSelectChat,
    onUploadFiles
}: KnowledgeBaseSidebarProps) {
    // State management
    const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
    const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);
    const [kbChats, setKBChats] = useState<KBChat[]>([]);
    const [kbDocuments, setKBDocuments] = useState<KBDocument[]>([]);
    const [activeChat, setActiveChat] = useState<KBChat | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isCreatingKB, setIsCreatingKB] = useState(false);
    const [isCreatingChat, setIsCreatingChat] = useState(false);
    const [docToDelete, setDocToDelete] = useState<KBDocument | null>(null);
    const [isDeletingDoc, setIsDeletingDoc] = useState(false);
    const [chatToDelete, setChatToDelete] = useState<KBChat | null>(null);
    const [isDeletingChat, setIsDeletingChat] = useState(false);
    const [documentsLoading, setDocumentsLoading] = useState(false);
    const [documentsError, setDocumentsError] = useState<string | null>(null);

    // Inline editing state for KB and Chat renaming
    const [editingKBId, setEditingKBId] = useState<string | null>(null);
    const [editingKBName, setEditingKBName] = useState('');
    const [editingChatId, setEditingChatId] = useState<string | null>(null);
    const [editingChatTitle, setEditingChatTitle] = useState('');
    const [isSavingEdit, setIsSavingEdit] = useState(false);

    // Create KB modal state
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newKBName, setNewKBName] = useState('');
    const [newKBDescription, setNewKBDescription] = useState('');

    // Load knowledge bases on mount
    useEffect(() => {
        loadKBs();
    }, []);

    // Load chats when KB is selected
    useEffect(() => {
        if (selectedKB) {
            loadChatsAndDocuments(selectedKB.id);
        }
    }, [selectedKB]);

    // Subscribe to real-time chat updates for auto-refresh when title changes or chat is deleted
    useEffect(() => {
        if (!selectedKB) return;

        let subscription: any;

        (async () => {
            const { supabase } = await import('@/utils/supabase');

            let debounceTimer: NodeJS.Timeout;

            subscription = supabase
                .channel('kb-chats-updates')
                .on(
                    'postgres_changes',
                    {
                        event: '*', // Listen to all events (INSERT, UPDATE, DELETE)
                        schema: 'public',
                        table: 'chats',
                        filter: `kb_id=eq.${selectedKB.id}`
                    },
                    (payload) => {
                        console.log('📡 Chat event (real-time):', payload.eventType, payload);

                        // Debounce the refresh to prevent spamming queries
                        clearTimeout(debounceTimer);
                        debounceTimer = setTimeout(() => {
                            loadChatsAndDocuments(selectedKB.id);
                        }, 500);
                    }
                )
                .subscribe((status) => {
                    console.log('📡 Subscription status:', status);
                });
        })();

        return () => {
            if (subscription) {
                subscription.unsubscribe();
            }
        };
    }, [selectedKB]);

    async function loadKBs() {
        try {
            setIsLoading(true);
            const kbs = await loadKnowledgeBases();
            setKnowledgeBases(kbs);
        } catch (error) {
            console.error('Failed to load knowledge bases:', error);
        } finally {
            setIsLoading(false);
        }
    }

    async function loadChatsAndDocuments(kbId: string) {
        try {
            setDocumentsLoading(true);
            setDocumentsError(null);

            const [chats, docs] = await Promise.all([
                loadKBChats(kbId),
                loadKBDocuments(kbId)
            ]);

            setKBChats(chats);
            setKBDocuments(docs);

            console.log('✅ Loaded documents:', docs.length);
        } catch (error) {
            console.error('Failed to load KB data:', error);
            setDocumentsError(error instanceof Error ? error.message : 'Unknown error');
        } finally {
            setDocumentsLoading(false);
        }
    }

    async function handleCreateKB() {
        if (!newKBName.trim()) return;

        try {
            setIsCreatingKB(true);
            const result = await createKnowledgeBase(newKBName, newKBDescription);

            // Reload knowledge bases
            await loadKBs();

            // Reset form and close modal
            setNewKBName('');
            setNewKBDescription('');
            setShowCreateModal(false);
        } catch (error) {
            console.error('Failed to create knowledge base:', error);
            alert('Failed to create knowledge base. Please try again.');
        } finally {
            setIsCreatingKB(false);
        }
    }

    async function handleCreateChat() {
        if (!selectedKB) return;

        try {
            setIsCreatingChat(true);
            const chat = await createKBChat(selectedKB.id, 'New Chat');

            // Reload chats
            await loadChatsAndDocuments(selectedKB.id);

            // Select the new chat
            setActiveChat(chat);
            onSelectChat(selectedKB.id, chat.id);
        } catch (error) {
            console.error('Failed to create chat:', error);
        } finally {
            setIsCreatingChat(false);
        }
    }

    async function handleDeleteKB(kbId: string, event: React.MouseEvent) {
        event.stopPropagation();

        if (!confirm('Are you sure you want to delete this knowledge base? This action cannot be undone.')) {
            return;
        }

        try {
            await deleteKnowledgeBase(kbId);
            await loadKBs();

            // Reset selection if deleted KB was selected
            if (selectedKB?.id === kbId) {
                setSelectedKB(null);
                setKBChats([]);
                setKBDocuments([]);
            }
        } catch (error) {
            console.error('Failed to delete knowledge base:', error);
            alert('Failed to delete knowledge base. Please try again.');
        }
    }

    function handleSelectKB(kb: KnowledgeBase) {
        setSelectedKB(kb);
        setActiveChat(null);
    }

    function handleSelectChat(chat: KBChat) {
        setActiveChat(chat);
        if (selectedKB) {
            onSelectChat(selectedKB.id, chat.id);
        }
    }

    function handleBack() {
        setSelectedKB(null);
        setKBChats([]);
        setKBDocuments([]);
        setActiveChat(null);
    }

    async function confirmDeleteDocument() {
        if (!selectedKB || !docToDelete) return;
        try {
            setIsDeletingDoc(true);
            await deleteKBDocument(selectedKB.id, docToDelete.id);
            await loadChatsAndDocuments(selectedKB.id);
            setDocToDelete(null);
        } catch (error) {
            console.error('Failed to delete document:', error);
            alert('Failed to delete document. Please try again.');
        } finally {
            setIsDeletingDoc(false);
        }
    }

    function handleDeleteClick(doc: KBDocument, event: React.MouseEvent) {
        event.stopPropagation();
        setDocToDelete(doc);
    }

    function cancelDeleteDocument() {
        if (isDeletingDoc) return;
        setDocToDelete(null);
    }

    // Chat delete handlers
    async function confirmDeleteChat() {
        if (!selectedKB || !chatToDelete) return;
        try {
            setIsDeletingChat(true);
            await deleteKBChat(chatToDelete.id);
            await loadChatsAndDocuments(selectedKB.id);
            setChatToDelete(null);
            // Clear active chat if it was deleted
            if (activeChat?.id === chatToDelete.id) {
                setActiveChat(null);
            }
        } catch (error) {
            console.error('Failed to delete chat:', error);
            alert('Failed to delete chat. Please try again.');
        } finally {
            setIsDeletingChat(false);
        }
    }

    function handleDeleteChatClick(chat: KBChat, event: React.MouseEvent) {
        event.stopPropagation();
        setChatToDelete(chat);
    }

    function cancelDeleteChat() {
        if (isDeletingChat) return;
        setChatToDelete(null);
    }

    // KB inline edit handlers
    function handleStartEditKB(kb: KnowledgeBase, event: React.MouseEvent) {
        event.stopPropagation();
        setEditingKBId(kb.id);
        setEditingKBName(kb.name);
    }

    async function handleSaveKBEdit() {
        if (!editingKBId || !editingKBName.trim()) return;
        try {
            setIsSavingEdit(true);
            await updateKnowledgeBase(editingKBId, { name: editingKBName.trim() });
            await loadKBs();
            setEditingKBId(null);
            setEditingKBName('');
        } catch (error) {
            console.error('Failed to rename knowledge base:', error);
            alert('Failed to rename knowledge base. Please try again.');
        } finally {
            setIsSavingEdit(false);
        }
    }

    function handleCancelKBEdit() {
        if (isSavingEdit) return;
        setEditingKBId(null);
        setEditingKBName('');
    }

    // Chat inline edit handlers
    function handleStartEditChat(chat: KBChat, event: React.MouseEvent) {
        event.stopPropagation();
        setEditingChatId(chat.id);
        setEditingChatTitle(chat.title);
    }

    async function handleSaveChatEdit() {
        if (!editingChatId || !editingChatTitle.trim()) return;
        try {
            setIsSavingEdit(true);
            await updateChatTitle(editingChatId, editingChatTitle.trim());
            if (selectedKB) {
                await loadChatsAndDocuments(selectedKB.id);
            }
            setEditingChatId(null);
            setEditingChatTitle('');
        } catch (error) {
            console.error('Failed to rename chat:', error);
            alert('Failed to rename chat. Please try again.');
        } finally {
            setIsSavingEdit(false);
        }
    }

    function handleCancelChatEdit() {
        if (isSavingEdit) return;
        setEditingChatId(null);
        setEditingChatTitle('');
    }

    // Render loading state
    if (isLoading) {
        return (
            <div className="h-full flex items-center justify-center bg-sidebar">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
            </div>
        );
    }

    // Level 1: Knowledge Base List
    if (!selectedKB) {
        return (
            <div className="h-full flex flex-col bg-sidebar">
                {/* Header */}
                <div className="p-4 border-b border-border bg-sidebar">
                    <div className="flex items-center justify-between">
                        <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
                            <BookOpen className="w-5 h-5 text-primary" />
                            <span>Knowledge Bases</span>
                        </h2>
                        <button
                            onClick={() => setShowCreateModal(true)}
                            className="p-1.5 hover:bg-muted rounded-lg transition-colors"
                            title="Create Knowledge Base"
                        >
                            <Plus className="w-5 h-5 text-foreground" />
                        </button>
                    </div>
                </div>

                {/* KB List */}
                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                    {knowledgeBases.length === 0 ? (
                        <div className="text-center py-12 px-4">
                            <BookOpen className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                            <p className="text-foreground/70 text-sm mb-4">
                                No knowledge bases yet
                            </p>
                            <button
                                onClick={() => setShowCreateModal(true)}
                                className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors text-sm font-medium"
                            >
                                Create Your First KB
                            </button>
                        </div>
                    ) : (
                        knowledgeBases.map((kb) => (
                            <div
                                key={kb.id}
                                onClick={() => editingKBId !== kb.id && handleSelectKB(kb)}
                                className={`p-3 bg-white rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-all group ${editingKBId === kb.id ? 'ring-2 ring-primary' : ''}`}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <div className="flex-1 min-w-0">
                                        {editingKBId === kb.id ? (
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="text"
                                                    value={editingKBName}
                                                    onChange={(e) => setEditingKBName(e.target.value)}
                                                    onClick={(e) => e.stopPropagation()}
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter') handleSaveKBEdit();
                                                        if (e.key === 'Escape') handleCancelKBEdit();
                                                    }}
                                                    className="flex-1 px-2 py-1 text-sm border border-border rounded bg-white focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                    autoFocus
                                                    disabled={isSavingEdit}
                                                />
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleSaveKBEdit(); }}
                                                    disabled={!editingKBName.trim() || isSavingEdit}
                                                    className="p-1 hover:bg-green-100 rounded transition-all disabled:opacity-50"
                                                    title="Save"
                                                >
                                                    {isSavingEdit ? (
                                                        <Loader2 className="w-4 h-4 animate-spin text-primary" />
                                                    ) : (
                                                        <Check className="w-4 h-4 text-green-600" />
                                                    )}
                                                </button>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleCancelKBEdit(); }}
                                                    disabled={isSavingEdit}
                                                    className="p-1 hover:bg-red-100 rounded transition-all disabled:opacity-50"
                                                    title="Cancel"
                                                >
                                                    <X className="w-4 h-4 text-red-600" />
                                                </button>
                                            </div>
                                        ) : (
                                            <h3 className="font-medium text-foreground text-sm truncate">
                                                {kb.name}
                                            </h3>
                                        )}
                                        {kb.description && editingKBId !== kb.id && (
                                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                                {kb.description}
                                            </p>
                                        )}
                                        {editingKBId !== kb.id && (
                                            <div className="mt-2 text-xs text-muted-foreground">
                                                {new Date(kb.created_at).toLocaleDateString()}
                                            </div>
                                        )}
                                    </div>
                                    {editingKBId !== kb.id && (
                                        <div className="flex items-center gap-1 flex-shrink-0">
                                            <button
                                                onClick={(e) => handleStartEditKB(kb, e)}
                                                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-muted rounded transition-all"
                                                title="Rename KB"
                                            >
                                                <Edit3 className="w-4 h-4 text-muted-foreground" />
                                            </button>
                                            <button
                                                onClick={(e) => handleDeleteKB(kb.id, e)}
                                                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-destructive/10 rounded transition-all"
                                                title="Delete KB"
                                            >
                                                <Trash2 className="w-4 h-4 text-destructive" />
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                </div>

                {/* Create KB Modal */}
                {showCreateModal && (
                    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                        <div className="bg-white rounded-xl max-w-md w-full p-5 sm:p-6 border border-border shadow-xl">
                            <h3 className="text-lg sm:text-xl font-display font-semibold text-foreground mb-4 sm:mb-6">
                                Create Knowledge Base
                            </h3>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground mb-2">
                                        Name *
                                    </label>
                                    <input
                                        type="text"
                                        value={newKBName}
                                        onChange={(e) => setNewKBName(e.target.value)}
                                        placeholder="My Research Project"
                                        className="w-full px-4 py-2.5 border border-border rounded-lg bg-white text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                                        autoFocus
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-foreground mb-2">
                                        Description (optional)
                                    </label>
                                    <textarea
                                        value={newKBDescription}
                                        onChange={(e) => setNewKBDescription(e.target.value)}
                                        placeholder="A collection of research papers and data..."
                                        rows={3}
                                        className="w-full px-4 py-2.5 border border-border rounded-lg bg-white text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary resize-none"
                                    />
                                </div>
                            </div>

                            <div className="flex gap-3 mt-6">
                                <button
                                    onClick={() => setShowCreateModal(false)}
                                    className="flex-1 px-4 py-2.5 border border-border text-foreground rounded-lg hover:bg-muted/50 transition-colors font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleCreateKB}
                                    disabled={!newKBName.trim() || isCreatingKB}
                                    className="flex-1 px-4 py-2.5 bg-primary text-white rounded-lg hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 font-medium"
                                >
                                    {isCreatingKB ? (
                                        <>
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                            Creating...
                                        </>
                                    ) : (
                                        'Create KB'
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // Level 2: Chat List for Selected KB
    return (
        <div className="h-full flex flex-col bg-sidebar">
            {/* Header with Back Button */}
            <div className="p-4 border-b border-border bg-sidebar">
                <button
                    onClick={handleBack}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover mb-6 transition-colors text-sm font-medium"
                >
                    <ArrowLeft className="w-4 h-4" />
                    <span>Back to Knowledge Bases</span>
                </button>

                <div className="flex items-center gap-2 mb-4">
                    <MessageSquare className="w-5 h-5 text-primary" />
                    <h2 className="text-base font-semibold text-foreground truncate">
                        Chats
                    </h2>
                </div>

                {/* Action Buttons */}
                <div className="flex flex-col sm:flex-row gap-2">
                    <button
                        onClick={handleCreateChat}
                        disabled={isCreatingChat}
                        className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-colors text-sm font-medium"
                    >
                        <Plus className="w-4 h-4" />
                        {isCreatingChat ? 'Creating...' : 'New Chat'}
                    </button>
                    <button
                        onClick={() => onUploadFiles(selectedKB.id)}
                        className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-accent text-accent-foreground rounded-lg hover:bg-accent/80 transition-colors text-sm font-medium"
                    >
                        <Upload className="w-4 h-4" />
                        Upload
                    </button>
                </div>
            </div>

            {/* Documents Section */}
            <div className="pt-6 px-4 pb-4 border-b border-border bg-sidebar">
                <h3 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-primary" />
                    Documents ({kbDocuments.length})
                </h3>

                {documentsLoading ? (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground p-2">
                        <Loader2 className="w-3 h-3 animate-spin text-primary" />
                        Loading documents...
                    </div>
                ) : documentsError ? (
                    <div className="text-xs text-destructive p-2 bg-destructive/10 rounded">
                        Failed to load documents
                    </div>
                ) : kbDocuments.length === 0 ? (
                    <div className="text-xs text-muted-foreground p-2 text-center bg-muted/30 rounded">
                        No documents yet
                        <button
                            onClick={() => onUploadFiles(selectedKB.id)}
                            className="block w-full mt-2 text-primary hover:text-primary-hover transition-colors font-medium"
                        >
                            Upload your first document
                        </button>
                    </div>
                ) : (
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                        {kbDocuments.map((doc) => (
                            <div
                                key={doc.id}
                                className="flex items-center gap-2 text-xs text-foreground p-2 bg-white rounded hover:bg-muted/30 transition-colors group"
                            >
                                <FileText className="w-3 h-3 flex-shrink-0 text-muted-foreground" />
                                <span className="truncate flex-1">{doc.filename}</span>
                                {doc.processing_status === 'completed' && (
                                    <Check className="w-3 h-3 text-green-600" />
                                )}
                                {doc.processing_status === 'processing' && (
                                    <Loader2 className="w-3 h-3 animate-spin text-primary" />
                                )}
                                {doc.processing_status === 'failed' && (
                                    <X className="w-3 h-3 text-destructive" />
                                )}
                                <button
                                    onClick={(e) => handleDeleteClick(doc, e)}
                                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-destructive/10 rounded transition-all"
                                    title="Delete document"
                                >
                                    <Trash2 className="w-3 h-3 text-destructive" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Chat List */}
            <div className="flex-1 overflow-y-auto pt-6 px-3 pb-3 space-y-1.5">
                {kbChats.length === 0 ? (
                    <div className="text-center py-12 px-4">
                        <MessageSquare className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                        <p className="text-foreground/70 text-sm mb-4">
                            No chats yet
                        </p>
                        <button
                            onClick={handleCreateChat}
                            className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors text-sm font-medium"
                        >
                            Start Your First Chat
                        </button>
                    </div>
                ) : (
                    kbChats.map((chat) => (
                        <div
                            key={chat.id}
                            onClick={() => editingChatId !== chat.id && handleSelectChat(chat)}
                            className={`p-3 rounded-lg cursor-pointer transition-all group ${editingChatId === chat.id
                                ? 'bg-muted/70 ring-2 ring-primary'
                                : activeChat?.id === chat.id
                                    ? 'bg-muted/70 border border-primary'
                                    : 'bg-white border border-transparent hover:bg-muted/30'
                                }`}
                        >
                            <div className="flex items-center gap-2">
                                <MessageSquare className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                                {editingChatId === chat.id ? (
                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                        <input
                                            type="text"
                                            value={editingChatTitle}
                                            onChange={(e) => setEditingChatTitle(e.target.value)}
                                            onClick={(e) => e.stopPropagation()}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') handleSaveChatEdit();
                                                if (e.key === 'Escape') handleCancelChatEdit();
                                            }}
                                            className="flex-1 px-2 py-1 text-sm border border-border rounded bg-white focus:outline-none focus:ring-2 focus:ring-primary/50"
                                            autoFocus
                                            disabled={isSavingEdit}
                                        />
                                        <button
                                            onClick={(e) => { e.stopPropagation(); handleSaveChatEdit(); }}
                                            disabled={!editingChatTitle.trim() || isSavingEdit}
                                            className="p-1 hover:bg-green-100 rounded transition-all disabled:opacity-50"
                                            title="Save"
                                        >
                                            {isSavingEdit ? (
                                                <Loader2 className="w-3 h-3 animate-spin text-primary" />
                                            ) : (
                                                <Check className="w-3 h-3 text-green-600" />
                                            )}
                                        </button>
                                        <button
                                            onClick={(e) => { e.stopPropagation(); handleCancelChatEdit(); }}
                                            disabled={isSavingEdit}
                                            className="p-1 hover:bg-red-100 rounded transition-all disabled:opacity-50"
                                            title="Cancel"
                                        >
                                            <X className="w-3 h-3 text-red-600" />
                                        </button>
                                    </div>
                                ) : (
                                    <>
                                        <h3 className="font-medium text-foreground text-sm truncate flex-1">
                                            {chat.title}
                                        </h3>
                                        <button
                                            onClick={(e) => handleStartEditChat(chat, e)}
                                            className="opacity-0 group-hover:opacity-100 p-1 hover:bg-muted rounded transition-all"
                                            title="Rename chat"
                                        >
                                            <Edit3 className="w-3 h-3 text-muted-foreground" />
                                        </button>
                                        <button
                                            onClick={(e) => handleDeleteChatClick(chat, e)}
                                            className="opacity-0 group-hover:opacity-100 p-1 hover:bg-destructive/10 rounded transition-all"
                                            title="Delete chat"
                                        >
                                            <Trash2 className="w-3 h-3 text-destructive" />
                                        </button>
                                    </>
                                )}
                            </div>
                            {editingChatId !== chat.id && (
                                <p className="text-xs text-muted-foreground mt-1">
                                    {new Date(chat.updated_at).toLocaleDateString()}
                                </p>
                            )}
                        </div>
                    ))
                )}
            </div>
            {docToDelete && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
                    <div className="bg-white border border-border rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
                        <div className="flex items-start gap-3">
                            <div className="p-2 rounded-full bg-destructive/10">
                                <Trash2 className="w-5 h-5 text-destructive" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-lg font-semibold text-foreground">Delete document?</h3>
                                <p className="text-sm text-muted-foreground mt-1">
                                    This action cannot be undone. The document "{docToDelete.filename}" will be removed.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={cancelDeleteDocument}
                                className="px-4 py-2 rounded-lg border border-border text-foreground hover:bg-muted/50 transition-colors font-medium"
                                disabled={isDeletingDoc}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmDeleteDocument}
                                className="px-4 py-2 rounded-lg bg-destructive text-white hover:bg-destructive/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed font-medium"
                                disabled={isDeletingDoc}
                            >
                                {isDeletingDoc ? 'Deleting...' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {chatToDelete && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
                    <div className="bg-white border border-border rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
                        <div className="flex items-start gap-3">
                            <div className="p-2 rounded-full bg-destructive/10">
                                <Trash2 className="w-5 h-5 text-destructive" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-lg font-semibold text-foreground">Delete chat?</h3>
                                <p className="text-sm text-muted-foreground mt-1">
                                    This action cannot be undone. The chat "{chatToDelete.title}" and all its messages will be removed.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={cancelDeleteChat}
                                className="px-4 py-2 rounded-lg border border-border text-foreground hover:bg-muted/50 transition-colors font-medium"
                                disabled={isDeletingChat}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmDeleteChat}
                                className="px-4 py-2 rounded-lg bg-destructive text-white hover:bg-destructive/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed font-medium"
                                disabled={isDeletingChat}
                            >
                                {isDeletingChat ? 'Deleting...' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
