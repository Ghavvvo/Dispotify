import { Music } from "lucide-react";
import { usePlayer } from "../../../context/PlayerContext.tsx";
import { useRef, useEffect, useState } from "react";


const STATIC_URL = import.meta.env.VITE_STATIC_URL || 'http:

export function Footer(){
    const { currentSong } = usePlayer();
    const audioRef = useRef<HTMLAudioElement>(null);
    const [retryCount, setRetryCount] = useState(0);
    const lastPositionRef = useRef(0);
    const isRetryingRef = useRef(false);

    
    const handleAudioError = (e: React.SyntheticEvent<HTMLAudioElement, Event>) => {
        const audio = audioRef.current;
        if (!audio || !currentSong || isRetryingRef.current) return;

        
        if (retryCount >= 5) {
            console.error('Max retry attempts reached. Playback failed.');
            isRetryingRef.current = false;
            return;
        }

        console.warn(`Audio playback error detected. Attempting to reconnect to new leader... (attempt ${retryCount + 1}/5)`);
        
        
        lastPositionRef.current = audio.currentTime || 0;
        isRetryingRef.current = true;

        
        const retryDelay = Math.min(1000 * Math.pow(2, retryCount), 16000);

        
        setTimeout(() => {
            if (audio && currentSong) {
                console.log(`Retrying playback from position ${lastPositionRef.current}s`);
                
                
                const cacheBuster = `?retry=${Date.now()}`;
                audio.src = STATIC_URL + currentSong.url + cacheBuster;
                
                audio.load();
                
                
                audio.addEventListener('loadedmetadata', () => {
                    audio.currentTime = lastPositionRef.current;
                }, { once: true });
                
                audio.play().then(() => {
                    console.log('✅ Playback resumed successfully on new leader');
                    setRetryCount(0);
                    isRetryingRef.current = false;
                }).catch((err) => {
                    console.error('❌ Failed to resume playback:', err);
                    setRetryCount(prev => prev + 1);
                    isRetryingRef.current = false;
                });
            }
        }, retryDelay);
    };

    
    const handleTimeUpdate = () => {
        if (audioRef.current && !isRetryingRef.current) {
            lastPositionRef.current = audioRef.current.currentTime;
        }
    };

    
    useEffect(() => {
        setRetryCount(0);
        lastPositionRef.current = 0;
        isRetryingRef.current = false;
    }, [currentSong?.id]);

    return (
        <footer className={'flex bg-black w-full h-40 p-6 justify-between items-center gap-6'}>
            <div className={'flex items-center h-full'}>
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
            
            <div className={'flex items-center justify-center w-full'}>
                {currentSong && (
                    <audio 
                        ref={audioRef}
                        controls 
                        autoPlay
                        src={STATIC_URL+currentSong.url}
                        className={'w-full max-w-2xl'}
                        onError={handleAudioError}
                        onTimeUpdate={handleTimeUpdate}
                    />
                )}
            </div>
            
            <div className={'w-64'}></div>
        </footer>
    )
}