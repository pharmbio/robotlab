comm -23 <(ls *db | sort) <(git ls-files | sort) | xargs mv -v -t archive
