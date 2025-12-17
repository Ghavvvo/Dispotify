import {Music, Play, Info, AlertTriangle} from "lucide-react";
import type { ISong } from "../../../types/ISong.ts";
import { usePlayer } from "../../../context/PlayerContext.tsx";
import { useState } from "react";
import { SongDetails } from "../../../components/SongDetails.tsx";

interface SongItemProps extends ISong {}

export function SongItem(song: SongItemProps) {
    const { playSong, currentSong } = usePlayer();
    const [isHovered, setIsHovered] = useState(false);
    const [showDetails, setShowDetails] = useState(false);
    
    const isCurrentSong = currentSong?.id === song.id;
    
    const handleClick = () => {
        playSong(song);
    };

    const handleInfoClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        setShowDetails(true);
    };
    
    return (
        <>
            <article 
                className={'flex flex-col cursor-pointer transition-transform hover:scale-105'}
                onClick={handleClick}
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
            >
                <div className={'bg-green-950 rounded-lg p-4 relative flex justify-center items-center'}>
                    <Music size={100} className={'text-green-600'}/>
                    {isHovered && (
                        <div className={'absolute inset-0 bg-black/50 rounded-lg flex items-center justify-center'}>
                            <Play size={50} className={'text-white'} fill="white"/>
                        </div>
                    )}
                    {isCurrentSong && (
                        <div className={'absolute bottom-2 right-2 bg-green-500 rounded-full p-1'}>
                            <div className={'w-2 h-2 bg-white rounded-full animate-pulse'}/>
                        </div>
                    )}
                    {/* Info button */}
                    <button
                        onClick={handleInfoClick}
                        className={'absolute top-2 right-2 bg-neutral-900/80 hover:bg-neutral-800 rounded-full p-2 transition-colors opacity-0 hover:opacity-100 group-hover:opacity-100'}
                        style={{ opacity: isHovered ? 1 : 0 }}
                    >
                        <Info size={20} className={'text-white'} />
                    </button>
                </div>
                <h4 className={`mt-4 text-xl font-semibold flex items-center gap-2 ${isCurrentSong ? 'text-green-500' : song.conflict_flag ? 'text-red-400' : 'text-neutral-100/80'}`}>
                    {song.nombre}
                    {song.conflict_flag && <AlertTriangle size={16} className="text-red-400" />}
                </h4>
                <p className={'text-neutral-100/60'}>{song.autor}</p>
            </article>
            
            <SongDetails 
                song={song}
                isOpen={showDetails}
                onClose={() => setShowDetails(false)}
            />
        </>
    )
}