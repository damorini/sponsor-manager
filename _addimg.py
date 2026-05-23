p = "catalog/models.py"
c = open(p, encoding="utf-8").read()
if "image = models.FileField" in c:
    print("gia' presente")
else:
    anc = '''    description = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Descrizione (multilingua)",
    )
'''
    add = anc + '''
    image = models.FileField(
        upload_to='services/images/',
        null=True,
        blank=True,
        verbose_name="Immagine",
        help_text="Foto dell'articolo mostrata nel catalogo.",
    )
'''
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,add,1))
        print("campo image aggiunto")
    else:
        print("ATTENZIONE: ancora non trovata")
