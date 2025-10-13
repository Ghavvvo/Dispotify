import {useState} from "react";
import type {ISong} from "../../../types/ISong.ts";
import {api} from "../../../api/api.ts";
import {toast} from "react-toastify";
import {toQueryParams} from "../../../utils/utils.ts";

export const useServerSongs = () => {
    const [songs, setSongs] = useState<ISong[]>()
    const [isGettingSongs, setIsGettingSongs] = useState(false)
    const [isUploadingSong, setIsUploadingSong] = useState(false)
    const [isDeletingSong, setIsDeletingSong] = useState(false)
    
    
    const getSongs = () => {
        setIsGettingSongs(true)
        api.get("music").then((resp) => {
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
    const uploadSong = (body: unknown, queryParams: object) => {
        setIsUploadingSong(true)
        api.post("music/upload?"+toQueryParams(queryParams), body).then((resp) => {
            console.log(resp)
        }).catch((e) => {
            console.error(e)
        })
        setIsUploadingSong(false)

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
    
    const downloadSong = (id: number) => {
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