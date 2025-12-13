import { Music } from "lucide-react";
import { usePlayer } from "../../../context/PlayerContext.tsx";

// Static files URL (points to the proxy)
const STATIC_URL = import.meta.env.VITE_STATIC_URL || 'http://localhost:3001';

export function Footer(){
    const { currentSong } = usePlayer();
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
                        controls 
                        autoPlay
                        src={STATIC_URL+currentSong.url}
                        className={'w-full max-w-2xl'}
                    />
                )}
            </div>
            
            <div className={'w-64'}></div>
        </footer>
    )
}