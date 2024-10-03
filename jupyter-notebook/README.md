Jypter Notebook for ArcGIS
==========================

The file [celantur-arcgis-example-v1.ipynb](./celantur-arcgis-example-v1.ipynb) contains the example code (Currently
POC version).

## Preparing
1. On the ArcGIS page [https://celantur.maps.arcgis.com/home/content.html](https://celantur.maps.arcgis.com/home/content.html)
   click to `New Item` button and proceed with creation of `Feature Layer`.
2. Then open that new Item, and open `Data` tab and select `Fields` sub-tab
3. Click to `Add` button (only if this field does not yet exist)
   * `Field Name`: `is_anonymized`
   * `Display Name`: `Is anonymized`
   * `Type`: `integer`
   * `Default Value`: `0`
   * Click `Add New Field`
4. Add images as attachment to points via Field Maps app. Make sure the same Feature Service Layer is specified in the Notebook code.
5. Run the code (described in [Code-running](#code-running) section)


## Code-running
Use [the example file](./celantur-arcgis-example-v1.ipynb) as a template and follow the next steps:
1. In the section of `! CREDENTIALS !` specify your credentials accordingly
2. Go to section `Main`
   * Adjust `layer_id` uid value to the corresponding layer you want to use.
   * Adjust params to your taste (Available parameters could be found in official celantur-doc: [https://doc.celantur.com/cloud-api/api-endpoints#create-anonymization-task](https://doc.celantur.com/cloud-api/api-endpoints#create-anonymization-task))
3. Run the code


## References
- [Notebooks in ArcGIS Pro](https://pro.arcgis.com/en/pro-app/latest/arcpy/get-started/pro-notebooks.htm)
- [Use ArcGIS API for Python in a notebook](https://doc.arcgis.com/en/arcgis-online/reference/use-the-arcgis-api-for-python-in-your-notebook.htm)