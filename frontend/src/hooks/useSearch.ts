import { useState, useCallback } from "react";
import type { ISong } from "../types/ISong.ts";
import { api } from "../api/api.ts";
import { toQueryParams } from "../utils/utils.ts";

export interface SearchFilters {
    q?: string;
    genero?: string;
    autor?: string;
    album?: string;
}

export type { SearchFilters as SearchFiltersType };

export const useSearch = () => {
    const [results, setResults] = useState<ISong[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const search = useCallback(async (filters: SearchFilters) => {
        setIsSearching(true);
        setError(null);

        try {
            // Filtrar solo los parámetros que tienen valor
            const params = Object.entries(filters).reduce((acc, [key, value]) => {
                if (value && value.trim() !== "") {
                    acc[key] = value;
                }
                return acc;
            }, {} as Record<string, string>);

            // Si no hay filtros, retornar array vacío
            if (Object.keys(params).length === 0) {
                setResults([]);
                setIsSearching(false);
                return [];
            }

            const queryString = toQueryParams(params);
            const response = await api.get(`music?${queryString}`);
            setResults(response);
            setIsSearching(false);
            return response;
        } catch (e) {
            console.error(e);
            setError("Error al buscar canciones");
            setIsSearching(false);
            return [];
        }
    }, []);

    const clearResults = useCallback(() => {
        setResults([]);
        setError(null);
    }, []);

    return {
        results,
        isSearching,
        error,
        search,
        clearResults,
    };
};
