'use client';

import { useState } from 'react';
import KBSidebar from '@/components/KBSidebar';
import KBChatInterface from '@/components/KBChatInterface';
import KBFileUpload from '@/components/KBFileUpload';
import Image from 'next/image';
import { Menu, X, Send } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function KnowledgeBasePage() {
    const [selectedKB, setSelectedKB] = useState<{ id: string; name: string } | null>(null);
    const [selectedChat, setSelectedChat] = useState<string | null>(null);
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [pendingUploadKB, setPendingUploadKB] = useState<string | null>(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    function handleSelectChat(kbId: string, chatId: string) {
        console.log('Selected chat:', { kbId, chatId });
        setSelectedKB({ id: kbId, name: 'Loading...' });
        setSelectedChat(chatId);
        // On mobile, close sidebar after selecting a chat
        setIsSidebarOpen(false);
    }

    function handleUploadFiles(kbId: string) {
        setPendingUploadKB(kbId);
        setShowUploadModal(true);
    }

    function handleUploadComplete() {
        console.log('Upload complete, refreshing...');
    }

    function handleCloseUpload() {
        setShowUploadModal(false);
        setPendingUploadKB(null);
    }

    return (
        <div className="min-h-screen bg-white text-foreground">
            <div className="h-screen flex flex-col overflow-hidden">
                {/* Header - ChatGPT Style */}
                <header className="h-14 border-b border-border bg-white flex items-center justify-between px-4 shadow-sm z-30">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                            className="p-2 -ml-2 hover:bg-muted rounded-lg md:hidden transition-colors"
                            aria-label="Toggle Sidebar"
                        >
                            {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                        </button>
                        <Image
                            src="/Geo-Logo1.png"
                            alt="DramaGPT Logo"
                            width={32}
                            height={32}
                            className="h-8 w-auto object-contain"
                        />
                        <h1 className="text-lg font-semibold text-foreground">
                            DramaGPT
                        </h1>
                    </div>
                </header>

                {/* Main Content */}
                <div className="flex-1 flex overflow-hidden relative bg-white">
                    {/* Sidebar Overlay for Mobile */}
                    <AnimatePresence>
                        {isSidebarOpen && (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.2 }}
                                className="fixed inset-0 bg-black/40 z-20 md:hidden backdrop-blur-sm"
                                onClick={() => setIsSidebarOpen(false)}
                            />
                        )}
                    </AnimatePresence>

                    {/* Sidebar */}
                    <div className="relative h-full z-30 md:z-0">
                        {/* Mobile Sidebar (Animated) */}
                        <AnimatePresence>
                            {isSidebarOpen && (
                                <motion.div
                                    initial={{ x: '-100%' }}
                                    animate={{ x: 0 }}
                                    exit={{ x: '-100%' }}
                                    transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                                    className="fixed inset-y-0 left-0 w-80 bg-sidebar z-30 shadow-2xl md:hidden border-r border-border"
                                >
                                    <KBSidebar
                                        onSelectChat={handleSelectChat}
                                        onUploadFiles={handleUploadFiles}
                                    />
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Desktop Sidebar (Static) */}
                        <div className="hidden md:block h-full w-80 bg-sidebar border-r border-border">
                            <KBSidebar
                                onSelectChat={handleSelectChat}
                                onUploadFiles={handleUploadFiles}
                            />
                        </div>
                    </div>

                    {/* Main Chat Area */}
                    <main className="flex-1 flex flex-col bg-white overflow-hidden relative">
                        {selectedKB && selectedChat ? (
                            <KBChatInterface
                                kbId={selectedKB.id}
                                chatId={selectedChat}
                                kbName={selectedKB.name}
                            />
                        ) : (
                            <div className="flex-1 flex flex-col bg-white">
                                {/* Empty state - just show disabled chat input */}
                                <div className="flex-1"></div>

                                {/* Disabled Chat Input Bar */}
                                <div className="border-t border-border bg-white p-4">
                                    <div className="max-w-4xl mx-auto">
                                        <div className="relative">
                                            <input
                                                type="text"
                                                disabled
                                                placeholder="Select a knowledge base and chat to get started..."
                                                className="w-full px-4 py-3 pr-12 border border-border rounded-lg bg-muted/30 text-muted-foreground placeholder-muted-foreground cursor-not-allowed focus:outline-none text-sm sm:text-base"
                                            />
                                            <button
                                                disabled
                                                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg bg-muted text-muted-foreground cursor-not-allowed"
                                            >
                                                <Send className="w-5 h-5" />
                                            </button>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-2 text-center px-4">
                                            Create or select a knowledge base from the sidebar to start chatting
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </main>
                </div>

                {/* Upload Modal */}
                {showUploadModal && pendingUploadKB && (
                    <KBFileUpload
                        kbId={pendingUploadKB}
                        onUploadComplete={handleUploadComplete}
                        onClose={handleCloseUpload}
                    />
                )}
            </div>
        </div>
    );
}
