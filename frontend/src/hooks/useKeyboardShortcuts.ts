import { useEffect } from 'react';
import { usePlayer } from '../context/PlayerContext.tsx';

export const useKeyboardShortcuts = () => {
    const { 
        togglePlayPause, 
        nextSong, 
        previousSong, 
        volume, 
        setVolume,
        currentSong 
    } = usePlayer();

    useEffect(() => {
        const handleKeyPress = (e: KeyboardEvent) => {
            
            if (e.target instanceof HTMLInputElement || 
                e.target instanceof HTMLTextAreaElement) {
                return;
            }

            switch(e.key) {
                case ' ': 
                    e.preventDefault();
                    if (currentSong) {
                        togglePlayPause();
                    }
                    break;
                    
                case 'ArrowRight':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        nextSong();
                    }
                    break;
                    
                case 'ArrowLeft':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        previousSong();
                    }
                    break;
                    
                case 'ArrowUp':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        const newVolume = Math.min(1, volume + 0.1);
                        setVolume(newVolume);
                    }
                    break;
                    
                case 'ArrowDown':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        const newVolume = Math.max(0, volume - 0.1);
                        setVolume(newVolume);
                    }
                    break;
                    
                case 'm':
                case 'M':
                    
                    e.preventDefault();
                    setVolume(volume > 0 ? 0 : 0.8);
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyPress);

        return () => {
            window.removeEventListener('keydown', handleKeyPress);
        };
    }, [togglePlayPause, nextSong, previousSong, volume, setVolume, currentSong]);
};