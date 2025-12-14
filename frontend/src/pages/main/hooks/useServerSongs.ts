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
                draggable: true,
            })
            setIsUploadingSong(false)
        }).catch((e) => {
            console.error(e)
            toast.error("Error al subir la canción", {
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
    
    /*const downloadSong = (id: number) => {
        setIsGettingSongs(true)
        api.get(`music/${id}/stream`).then((resp) => {
            setSongs(resp)
        }).catch((e) => {
            console.error(e)
            toast.error(e, {
                position: "top-right",
                autoClose: 3000,
                hideProgressBar: false,
                closeOnClick: true,
                pauseOnHover: true,
                draggable: true,
            })

        })
        setIsGettingSongs(false)
    }
    */
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