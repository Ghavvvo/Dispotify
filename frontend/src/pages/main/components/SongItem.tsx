import {Music, Play} from "lucide-react";
import type { ISong } from "../../../types/ISong.ts";
import { usePlayer } from "../../../context/PlayerContext.tsx";
import { useState } from "react";

interface SongItemProps extends ISong {}

export function SongItem(song: SongItemProps) {
    const { playSong, currentSong } = usePlayer();
    const [isHovered, setIsHovered] = useState(false);
    
    const isCurrentSong = currentSong?.id === song.id;
    
    const handleClick = () => {
        playSong(song);
    };
    
    return (
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
            </div>
            <h4 className={`mt-4 text-xl font-semibold ${isCurrentSong ? 'text-green-500' : 'text-neutral-100/80'}`}>
                {song.nombre}
            </h4>
            <p className={'text-neutral-100/60'}>{song.autor}</p>
        </article>
    )
}