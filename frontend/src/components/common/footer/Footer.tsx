import {Play, Pause, SkipBack, SkipForward, Volume2, ListMusic, Music} from "lucide-react";
import { usePlayer } from "../../../context/PlayerContext.tsx";
import { formatTime } from "../../../utils/formatTime.ts";
import React, { useRef, useState } from "react";

export function Footer(){
    const { 
        currentSong, 
        isPlaying, 
        currentTime, 
        duration, 
        volume,
        togglePlayPause,
        seekTo,
        setVolume,
        nextSong,
        previousSong
    } = usePlayer();
    
    const [isDraggingProgress, setIsDraggingProgress] = useState(false);
    const [isDraggingVolume, setIsDraggingVolume] = useState(false);
    const progressRef = useRef<HTMLDivElement>(null);
    const volumeRef = useRef<HTMLDivElement>(null);
    
    const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (!progressRef.current || !duration) return;
        
        const rect = progressRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percentage = x / rect.width;
        const newTime = percentage * duration;
        
        seekTo(newTime);
    };
    
    const handleProgressMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        setIsDraggingProgress(true);
        handleProgressClick(e);
    };
    
    const handleProgressMouseMove = (e: MouseEvent) => {
        if (!isDraggingProgress || !progressRef.current || !duration) return;
        
        const rect = progressRef.current.getBoundingClientRect();
        const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const percentage = x / rect.width;
        const newTime = percentage * duration;
        
        seekTo(newTime);
    };
    
    const handleProgressMouseUp = () => {
        setIsDraggingProgress(false);
    };
    
    const handleVolumeClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (!volumeRef.current) return;
        
        const rect = volumeRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percentage = x / rect.width;
        
        setVolume(percentage);
    };
    
    const handleVolumeMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        setIsDraggingVolume(true);
        handleVolumeClick(e);
    };
    
    const handleVolumeMouseMove = (e: MouseEvent) => {
        if (!isDraggingVolume || !volumeRef.current) return;
        
        const rect = volumeRef.current.getBoundingClientRect();
        const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const percentage = x / rect.width;
        
        setVolume(percentage);
    };
    
    const handleVolumeMouseUp = () => {
        setIsDraggingVolume(false);
    };
    
    // Global mouse event listeners for dragging
    React.useEffect(() => {
        if (isDraggingProgress) {
            document.addEventListener('mousemove', handleProgressMouseMove);
            document.addEventListener('mouseup', handleProgressMouseUp);
            
            return () => {
                document.removeEventListener('mousemove', handleProgressMouseMove);
                document.removeEventListener('mouseup', handleProgressMouseUp);
            };
        }
    }, [isDraggingProgress]);
    
    React.useEffect(() => {
        if (isDraggingVolume) {
            document.addEventListener('mousemove', handleVolumeMouseMove);
            document.addEventListener('mouseup', handleVolumeMouseUp);
            
            return () => {
                document.removeEventListener('mousemove', handleVolumeMouseMove);
                document.removeEventListener('mouseup', handleVolumeMouseUp);
            };
        }
    }, [isDraggingVolume]);
    
    const progressPercentage = duration > 0 ? (currentTime / duration) * 100 : 0;
    const volumePercentage = volume * 100;
    
    return (
        <footer className={'flex bg-black w-full h-40 p-6 justify-between items-center'}>
            <div className={'flex items-center h-full w-full'}>
                {currentSong ? (
                    <>
                        <div className={'bg-green-950 h-full rounded-lg p-4 flex items-center justify-center'}>
                            <Music size={40} className={'text-green-600'}/>
                        </div>
                        <div className={'flex flex-col justify-center ml-5'}>
                            <h4 className={'text-neutral-100 text-xl font-semibold'}>
                                {currentSong.nombre}
                            </h4>
                            <p className={'text-neutral-100/60'}>{currentSong.autor}</p>
                        </div>
                    </>
                ) : (
                    <div className={'flex items-center'}>
                        <div className={'bg-neutral-800 h-20 w-20 rounded-lg'}/>
                        <div className={'flex flex-col justify-center ml-5'}>
                            <h4 className={'text-neutral-100/40 text-xl'}>
                                No hay canción
                            </h4>
                            <p className={'text-neutral-100/30'}>Selecciona una canción</p>
                        </div>
                    </div>
                )}
            </div>
            
            <div className={'flex items-center gap-4 flex-col justify-center w-full'}>
                <div className={'flex justify-center items-center space-x-10'}>
                    <button 
                        onClick={previousSong}
                        className={'hover:scale-110 transition-transform disabled:opacity-50'}
                        disabled={!currentSong}
                    >
                        <SkipBack fill={'#f5f5f5'} stroke={'#f5f5f5'} width={30} height={30} />
                    </button>
                    <button 
                        onClick={togglePlayPause}
                        className={'flex justify-center items-center bg-neutral-100 rounded-full p-3 hover:scale-110 transition-transform disabled:opacity-50'}
                        disabled={!currentSong}
                    >
                        {isPlaying ? (
                            <Pause fill={'#000'} size={24}/>
                        ) : (
                            <Play fill={'#000'} size={24} style={{marginLeft: '2px'}}/>
                        )}
                    </button>
                    <button 
                        onClick={nextSong}
                        className={'hover:scale-110 transition-transform disabled:opacity-50'}
                        disabled={!currentSong}
                    >
                        <SkipForward fill={'#f5f5f5'} stroke={'#f5f5f5'} width={30} height={30} />
                    </button>
                </div>
                
                <div className={'flex items-center gap-2 w-full'}>
                    <p className={'text-neutral-100/60 text-sm min-w-[40px] text-right'}>
                        {formatTime(currentTime)}
                    </p>
                    <div 
                        ref={progressRef}
                        className={'relative w-full h-1 bg-neutral-600 rounded-full cursor-pointer group'}
                        onMouseDown={handleProgressMouseDown}
                        onClick={handleProgressClick}
                    >
                        <div 
                            className={'absolute h-full bg-neutral-100 rounded-full pointer-events-none transition-all group-hover:bg-green-500'}
                            style={{width: `${progressPercentage}%`}}
                        />
                        <div 
                            className={'absolute h-3 w-3 bg-white rounded-full -top-1 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity'}
                            style={{left: `${progressPercentage}%`, transform: 'translateX(-50%)'}}
                        />
                    </div>
                    <p className={'text-neutral-100/60 text-sm min-w-[40px]'}>
                        {formatTime(duration)}
                    </p>
                </div>
            </div>
            
            <div className={'flex items-center gap-4 justify-end w-full'}>
                <ListMusic stroke={'#f5f5f5'} strokeWidth={2} className={'opacity-80 hover:opacity-100 cursor-pointer'} />
                <div className={'flex items-center gap-4 justify-center size-fit'}>
                    <Volume2 stroke={'#f5f5f5'} strokeWidth={2} className={'opacity-80'}/>
                    <div 
                        ref={volumeRef}
                        className={'relative w-40 h-1 bg-neutral-600 rounded-full cursor-pointer group'}
                        onMouseDown={handleVolumeMouseDown}
                        onClick={handleVolumeClick}
                    >
                        <div 
                            className={'absolute h-full bg-neutral-100 rounded-full pointer-events-none transition-all group-hover:bg-green-500'}
                            style={{width: `${volumePercentage}%`}}
                        />
                        <div 
                            className={'absolute h-3 w-3 bg-white rounded-full -top-1 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity'}
                            style={{left: `${volumePercentage}%`, transform: 'translateX(-50%)'}}
                        />
                    </div>
                </div>
            </div>
        </footer>
    )
}