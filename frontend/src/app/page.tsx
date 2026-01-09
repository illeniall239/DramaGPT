'use client';

import { useState } from 'react';
import KBSidebar from '@/components/KBSidebar';
import KBChatInterface from '@/components/KBChatInterface';
import KBFileUpload from '@/components/KBFileUpload';
import Image from 'next/image';

export default function KnowledgeBasePage() {
    const [selectedKB, setSelectedKB] = useState<{ id: string; name: string } | null>(null);
    const [selectedChat, setSelectedChat] = useState<string | null>(null);
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [pendingUploadKB, setPendingUploadKB] = useState<string | null>(null);

    function handleSelectChat(kbId: string, chatId: string) {
        console.log('Selected chat:', { kbId, chatId });
        setSelectedKB({ id: kbId, name: 'Loading...' });
        setSelectedChat(chatId);
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
            <div className="h-screen flex flex-col">
                {/* Header - ChatGPT Style */}
                <header className="h-14 border-b border-border bg-white flex items-center justify-between px-4 shadow-sm">
                    <div className="flex items-center gap-2">
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
                <div className="flex-1 flex overflow-hidden bg-white">
                    {/* Sidebar */}
                    <div className="w-80 border-r border-border bg-sidebar overflow-y-auto">
                        <KBSidebar
                            onSelectChat={handleSelectChat}
                            onUploadFiles={handleUploadFiles}
                        />
                    </div>

                    {/* Main Chat Area */}
                    <div className="flex-1 flex flex-col bg-white">
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
                                                className="w-full px-4 py-3 pr-12 border border-border rounded-lg bg-muted/30 text-muted-foreground placeholder-muted-foreground cursor-not-allowed focus:outline-none"
                                            />
                                            <button
                                                disabled
                                                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg bg-muted text-muted-foreground cursor-not-allowed"
                                            >
                                                <svg
                                                    xmlns="http://www.w3.org/2000/svg"
                                                    viewBox="0 0 24 24"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    strokeWidth="2"
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    className="w-5 h-5"
                                                >
                                                    <path d="M22 2L11 13" />
                                                    <path d="M22 2L15 22L11 13L2 9L22 2Z" />
                                                </svg>
                                            </button>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-2 text-center">
                                            Create or select a knowledge base from the sidebar to start chatting
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
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
