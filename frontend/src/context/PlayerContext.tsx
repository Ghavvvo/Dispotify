import {createContext, useContext, useState, type ReactNode} from 'react';
import type { ISong } from '../types/ISong.ts';

interface PlayerContextType {
    currentSong: ISong | null;
    playSong: (song: ISong) => void;
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

    const playSong = (song: ISong) => {
        setCurrentSong(song);
    };

    const value: PlayerContextType = {
        currentSong,
        playSong,
    };

    return (
        <PlayerContext.Provider value={value}>
            {children}
        </PlayerContext.Provider>
    );
};