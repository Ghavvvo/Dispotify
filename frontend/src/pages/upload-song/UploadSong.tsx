import {type SubmitHandler, useForm,} from 'react-hook-form'
import {useServerSongs} from "../main/hooks/useServerSongs.ts";

interface FormData {
    nombre: string
    autor: string
    album: string
    genero: string
    file: FileList
}

export function UploadSong() {
    const {handleSubmit, register} = useForm<FormData>()
    const {uploadSong} = useServerSongs()

    const onSubmit: SubmitHandler<FormData> = async (data: FormData) => {
        const formData = new FormData();
        formData.append('file', data.file[0]);
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { file, ...processed } = data;
        uploadSong(formData, processed);
    }

    return (
        <section className={'size-full'}>
            <h1 className={'text-neutral-100 text-3xl font-bold'}>Subir canción</h1>
            <form 
                className={'text-white flex flex-col mt-20 space-y-4'}
                onSubmit={handleSubmit(onSubmit)}>
                <div>
                    <label className="block text-sm font-medium mb-1">Nombre</label>
                    <input
                        {...register('nombre', { required: true })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">Autor</label>
                    <input
                        {...register('autor', { required: true })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">Álbum</label>
                    <input
                        {...register('album', { required: true })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">Género</label>
                    <input
                        {...register('genero', { required: true })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">Archivo</label>
                    <input
                        {...register('file', { required: true })}
                        type={"file"}
                        accept="audio/*"
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                </div>
                
                
                <button type="submit" className="hover:bg-green-600 hover:cursor-pointer mt-4 px-4 py-2 bg-green-500 text-green-950 font-semibold rounded-md">
                    Subir canción
                </button>
            </form>
        </section>
    )
}