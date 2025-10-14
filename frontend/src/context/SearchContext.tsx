import {createContext, type ReactNode, useContext, useState} from "react";
import type { ISong } from "../types/ISong.ts";
import { useSearch, type SearchFilters } from "../hooks/useSearch.ts";

interface SearchContextType {
    searchResults: ISong[];
    isSearching: boolean;
    searchError: string | null;
    activeFilters: SearchFilters;
    performSearch: (filters: SearchFilters) => Promise<ISong[]>;
    clearSearch: () => void;
    setActiveFilters: (filters: SearchFilters) => void;
}

const SearchContext = createContext<SearchContextType | undefined>(undefined);

export const SearchProvider = ({ children }: { children: ReactNode }) => {
    const { results, isSearching, error, search, clearResults } = useSearch();
    const [activeFilters, setActiveFilters] = useState<SearchFilters>({});

    const performSearch = async (filters: SearchFilters) => {
        setActiveFilters(filters);
        return await search(filters);
    };

    const clearSearch = () => {
        clearResults();
        setActiveFilters({});
    };

    return (
        <SearchContext.Provider
            value={{
                searchResults: results,
                isSearching,
                searchError: error,
                activeFilters,
                performSearch,
                clearSearch,
                setActiveFilters,
            }}
        >
            {children}
        </SearchContext.Provider>
    );
};

export const useSearchContext = () => {
    const context = useContext(SearchContext);
    if (context === undefined) {
        throw new Error("useSearchContext must be used within a SearchProvider");
    }
    return context;
};

export type { SearchFilters };
