import { X, Music, User, Disc, Tag, HardDrive, Calendar } from "lucide-react";
import type { ISong } from "../types/ISong.ts";

interface SongDetailsProps {
    song: ISong;
    isOpen: boolean;
    onClose: () => void;
}

export function SongDetails({ song, isOpen, onClose }: SongDetailsProps) {
    if (!isOpen) return null;

    const formatFileSize = (bytes: number): string => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    };

    const formatDate = (date: Date): string => {
        return new Date(date).toLocaleDateString('es-ES', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    return (
        <div 
            className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
            onClick={onClose}
        >
            <div 
                className="bg-neutral-900 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="sticky top-0 bg-neutral-900 border-b border-neutral-800 p-6 flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-white">Detalles de la canción</h2>
                    <button
                        onClick={onClose}
                        className="text-neutral-400 hover:text-white transition-colors"
                    >
                        <X size={24} />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">
                    {/* Album Art Placeholder */}
                    <div className="bg-green-950 rounded-lg p-8 mb-6 flex items-center justify-center">
                        <Music size={120} className="text-green-600" />
                    </div>

                    {/* Song Info Grid */}
                    <div className="space-y-4">
                        {/* Nombre */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <Music className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Nombre</p>
                                <p className="text-white text-lg font-semibold">{song.nombre}</p>
                            </div>
                        </div>

                        {/* Autor */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <User className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Autor</p>
                                <p className="text-white text-lg">{song.autor}</p>
                            </div>
                        </div>

                        {/* Album */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <Disc className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Álbum</p>
                                <p className="text-white text-lg">{song.album}</p>
                            </div>
                        </div>

                        {/* Genero */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <Tag className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Género</p>
                                <p className="text-white text-lg">{song.genero}</p>
                            </div>
                        </div>


                        {/* File Size */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <HardDrive className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Tamaño del archivo</p>
                                <p className="text-white text-lg">{formatFileSize(song.file_size)}</p>
                            </div>
                        </div>

                        {/* Created At */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <Calendar className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Fecha de creación</p>
                                <p className="text-white text-lg">{formatDate(song.created_at)}</p>
                            </div>
                        </div>

                        {/* Updated At */}
                        <div className="flex items-start gap-3 p-4 bg-neutral-800/50 rounded-lg">
                            <Calendar className="text-green-500 mt-1 flex-shrink-0" size={20} />
                            <div className="flex-1">
                                <p className="text-neutral-400 text-sm mb-1">Última actualización</p>
                                <p className="text-white text-lg">{formatDate(song.updated_at)}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
