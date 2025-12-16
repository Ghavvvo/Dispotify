import {useState} from "react";
import type {ISong} from "../../../types/ISong.ts";
import {api} from "../../../api/api.ts";
import {toast} from "react-toastify";

export const useServerSongs = () => {
    const [songs, setSongs] = useState<ISong[]>()
    const [isGettingSongs, setIsGettingSongs] = useState(false)
    const [isUploadingSong, setIsUploadingSong] = useState(false)
    const [isDeletingSong, setIsDeletingSong] = useState(false)
    
    
    const getSongs = () => {
        setIsGettingSongs(true)
        api.get("music/").then((resp) => {
            setSongs(resp)
            setIsGettingSongs(false)
        }).catch((e) => {
            console.error(e)
            toast.error("Error al cargar las canciones", {
                position: "top-right",
                autoClose: 3000,
                hideProgressBar: false,
                closeOnClick: true,
                pauseOnHover: true,
                draggable: true,
            })
            setIsGettingSongs(false)
        })
    }
    const uploadSong = (body: unknown) => {
        setIsUploadingSong(true)
        api.post("music/upload", body).then((resp) => {
            console.log(resp)
            toast.success("Canción subida correctamente", {
                position: "top-right",
                autoClose: 3000,
                hideProgressBar: false,
                closeOnClick: true,
                pauseOnHover: true,
                draggable: true,                    // Ignorar error de parseo

            })
            setIsUploadingSong(false)
        }).catch((e) => {
            console.error(e)
            let errorMessage = "Error al subir la canción";

            if (e instanceof Error) {
                try {
                    const errorData = JSON.parse(e.message);
                    if (errorData.detail) {
                        errorMessage = errorData.detail;
                        if (errorMessage === "Duplicate MP3 file detected") {
                            errorMessage = "El archivo MP3 ya existe.";
                        } else if (errorMessage === "Song with same name and author already exists") {
                            errorMessage = "Ya existe una canción con el mismo nombre y autor.";
                        }
                    }
                } catch {
                }
            }

            toast.error(errorMessage, {
                position: "top-right",
                autoClose: 3000,
                hideProgressBar: false,
                closeOnClick: true,
                pauseOnHover: true,
                draggable: true,
            })
            setIsUploadingSong(false)
        })

    }
    const deleteSong = async (id: number) => {
        setIsDeletingSong(true)
        api.deleteReq("music", id).then((resp => {
            console.log(resp)
        })).catch((e) => {
            console.error(e)
        })
        setIsDeletingSong(false)
    }
    
    
    return {
        songs,
        getSongs,
        uploadSong,
        deleteSong,
        isDeletingSong,
        isGettingSongs,
        isUploadingSong,
    }
}