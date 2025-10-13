import {Search, Upload} from "lucide-react";
import { useNavigate } from "react-router-dom";

export function Topbar() {
    const navigate = useNavigate()

    return (
        <header className={'flex w-full h-24 items-center justify-center px-4 py-3 bg-black relative'}>
            <div 
                className={'hover:cursor-pointer flex items-center gap-4 absolute left-4 top-1/2 transform -translate-y-1/2'}
                onClick={() => navigate("/") }
            >
                <img src={'/spotify.png'} alt={'spotify'} className={'w-12 h-12'} />
                <h2 className={'text-[#40B26B] text-2xl font-bold'}>Dispotify</h2>
            </div>
            <div className={'relative w-1/4 h-full'}>
                <input
                    className={'w-full h-full rounded-full bg-[#1F1F1F] placeholder:text-neutral-100/50 text-neutral-100 px-4 pl-14'}
                    placeholder={'¿Qué quieres reproducir?'}
                />
                <Search className={'absolute left-4 top-1/2 transform -translate-y-1/2 text-neutral-100/50 w-6 h-6'} />
            </div>
            
            <button className={'flex gap-4 hover:from-green-500 transition-all hover:cursor-pointer absolute right-4 top-1/2 transform -translate-y-1/2 bg-white rounded-lg px-4 py-2 font-semibold bg-gradient-to-r from-green-400 to-green-500'}
                onClick={() => {
                    navigate("upload-song")
                }}
            >
                Subir canción
                <Upload width={18} strokeWidth={2}/>
            </button>
        </header>
    )
}
