import { useEffect, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { usePlayer } from '../context/PlayerContext.tsx';

export function VolumeIndicator() {
    const { volume } = usePlayer();
    const [showIndicator, setShowIndicator] = useState(false);
    const [lastVolume, setLastVolume] = useState(volume);

    useEffect(() => {
        if (volume !== lastVolume) {
            setShowIndicator(true);
            setLastVolume(volume);

            const timer = setTimeout(() => {
                setShowIndicator(false);
            }, 1500);

            return () => clearTimeout(timer);
        }
    }, [volume, lastVolume]);

    if (!showIndicator) return null;

    return (
        <div className="fixed top-20 right-4 bg-black/90 rounded-lg p-4 flex items-center gap-3 z-50 animate-fade-in">
            {volume === 0 ? (
                <VolumeX className="text-white" size={24} />
            ) : (
                <Volume2 className="text-white" size={24} />
            )}
            <div className="w-32 h-2 bg-neutral-700 rounded-full overflow-hidden">
                <div 
                    className="h-full bg-green-500 transition-all duration-200"
                    style={{ width: `${volume * 100}%` }}
                />
            </div>
            <span className="text-white text-sm min-w-[40px] text-right">
                {Math.round(volume * 100)}%
            </span>
        </div>
    );
}