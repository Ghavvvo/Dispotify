import { createContext, useContext, useState, useRef, useEffect, ReactNode } from 'react';
import type { ISong } from '../types/ISong.ts';

interface PlayerContextType {
    currentSong: ISong | null;
    isPlaying: boolean;
    currentTime: number;
    duration: number;
    volume: number;
    playlist: ISong[];
    playSong: (song: ISong) => void;
    pauseSong: () => void;
    resumeSong: () => void;
    togglePlayPause: () => void;
    seekTo: (time: number) => void;
    setVolume: (volume: number) => void;
    nextSong: () => void;
    previousSong: () => void;
    setPlaylist: (songs: ISong[]) => void;
}

const PlayerContext = createContext<PlayerContextType | undefined>(undefined);

export const usePlayer = () => {
    const context = useContext(PlayerContext);
    if (!context) {
        throw new Error('usePlayer must be used within a PlayerProvider');
    }
    return context;
};

interface PlayerProviderProps {
    children: ReactNode;
}

export const PlayerProvider = ({ children }: PlayerProviderProps) => {
    const [currentSong, setCurrentSong] = useState<ISong | null>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [volume, setVolumeState] = useState(0.8);
    const [playlist, setPlaylistState] = useState<ISong[]>([]);
    const [currentIndex, setCurrentIndex] = useState(-1);
    
    const audioRef = useRef<HTMLAudioElement | null>(null);

    useEffect(() => {
        // Crear el elemento de audio
        audioRef.current = new Audio();
        audioRef.current.volume = volume;

        // Event listeners
        const audio = audioRef.current;
        
        const handleTimeUpdate = () => {
            setCurrentTime(audio.currentTime);
        };

        const handleLoadedMetadata = () => {
            setDuration(audio.duration);
        };

        const handleEnded = () => {
            nextSong();
        };

        audio.addEventListener('timeupdate', handleTimeUpdate);
        audio.addEventListener('loadedmetadata', handleLoadedMetadata);
        audio.addEventListener('ended', handleEnded);

        return () => {
            audio.removeEventListener('timeupdate', handleTimeUpdate);
            audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
            audio.removeEventListener('ended', handleEnded);
            audio.pause();
        };
    }, []);

    const playSong = (song: ISong) => {
        if (!audioRef.current) return;

        // Si es la misma canción, solo toggle play/pause
        if (currentSong?.id === song.id && isPlaying) {
            pauseSong();
            return;
        } else if (currentSong?.id === song.id && !isPlaying) {
            resumeSong();
            return;
        }

        // Buscar el índice de la canción en la playlist
        const songIndex = playlist.findIndex(s => s.id === song.id);
        if (songIndex !== -1) {
            setCurrentIndex(songIndex);
        }

        // Cargar nueva canción
        const streamUrl = `http://127.0.0.1:8000/api/v1/music/${song.id}/stream`;
        audioRef.current.src = streamUrl;
        audioRef.current.load();
        
        setCurrentSong(song);
        setCurrentTime(0);
        
        // Reproducir
        audioRef.current.play()
            .then(() => {
                setIsPlaying(true);
            })
            .catch(error => {
                console.error('Error playing audio:', error);
                setIsPlaying(false);
            });
    };

    const pauseSong = () => {
        if (audioRef.current && isPlaying) {
            audioRef.current.pause();
            setIsPlaying(false);
        }
    };

    const resumeSong = () => {
        if (audioRef.current && !isPlaying && currentSong) {
            audioRef.current.play()
                .then(() => {
                    setIsPlaying(true);
                })
                .catch(error => {
                    console.error('Error resuming audio:', error);
                });
        }
    };

    const togglePlayPause = () => {
        if (!currentSong) return;
        
        if (isPlaying) {
            pauseSong();
        } else {
            resumeSong();
        }
    };

    const seekTo = (time: number) => {
        if (audioRef.current) {
            audioRef.current.currentTime = time;
            setCurrentTime(time);
        }
    };

    const setVolume = (newVolume: number) => {
        const clampedVolume = Math.max(0, Math.min(1, newVolume));
        setVolumeState(clampedVolume);
        if (audioRef.current) {
            audioRef.current.volume = clampedVolume;
        }
    };

    const nextSong = () => {
        if (playlist.length === 0) return;
        
        let nextIndex = currentIndex + 1;
        if (nextIndex >= playlist.length) {
            nextIndex = 0; // Volver al inicio de la lista
        }
        
        const nextSong = playlist[nextIndex];
        if (nextSong) {
            setCurrentIndex(nextIndex);
            playSong(nextSong);
        }
    };

    const previousSong = () => {
        if (playlist.length === 0) return;
        
        // Si la canción actual ha avanzado más de 3 segundos, reiniciar desde el principio
        if (currentTime > 3) {
            seekTo(0);
            return;
        }
        
        let prevIndex = currentIndex - 1;
        if (prevIndex < 0) {
            prevIndex = playlist.length - 1; // Ir al final de la lista
        }
        
        const prevSong = playlist[prevIndex];
        if (prevSong) {
            setCurrentIndex(prevIndex);
            playSong(prevSong);
        }
    };

    const setPlaylist = (songs: ISong[]) => {
        setPlaylistState(songs);
        // Si hay una canción actual, actualizar su índice en la nueva playlist
        if (currentSong) {
            const newIndex = songs.findIndex(s => s.id === currentSong.id);
            setCurrentIndex(newIndex);
        }
    };

    const value: PlayerContextType = {
        currentSong,
        isPlaying,
        currentTime,
        duration,
        volume,
        playlist,
        playSong,
        pauseSong,
        resumeSong,
        togglePlayPause,
        seekTo,
        setVolume,
        nextSong,
        previousSong,
        setPlaylist,
    };

    return (
        <PlayerContext.Provider value={value}>
            {children}
        </PlayerContext.Provider>
    );
};