import arcpy,os,sys
from datetime import datetime


###########  C:\Progra~1\ArcGIS\Pro\bin\Python\Scripts\propy FindWaterfalls.py D:\Sourcecode\WaterFalls\data.gdb\DEM 25 10 10


arcpy.env.overwriteOutput = True

script_path = os.path.dirname(os.path.realpath(sys.argv[0]))
data  = script_path + '\\data.gdb\\'
scratchpath = script_path + r'\scratch'
output_gdb = script_path + r'\\scratch\\streamdata.gdb'

###  Use mask to extract this from KYAbove.  Dont get too crazy with the size or you'll be here all day
dem_extract = sys.argv[1]
watershed_acreage_filter = sys.argv[2]
reach_distance = sys.argv[3]
height_filter = sys.argv[4]



def PrepareWorkspace():

    print ("Create folder: " + script_path + r'\scratch')
    if not os.path.exists(script_path + r'\scratch'):
        os.makedirs(script_path + r'\scratch')

    print("Make scratch geodatabase")
    if not arcpy.Exists(output_gdb):
        #arcpy.Delete_management(output_gdb, "Workspace")
        arcpy.CreateFileGDB_management(scratchpath, "streamdata")


def DeriveSteams():

    print("Fill")
    Fill_Extract1 = arcpy.sa.Fill(in_surface_raster=dem_extract, z_limit=None)
    Fill_Extract1.save(output_gdb + '\\fill')

    print("FlowDirection")
    FlowDir_Fill1 = arcpy.sa.FlowDirection(in_surface_raster=output_gdb + '\\fill', force_flow="NORMAL", out_drop_raster='', flow_direction_type="D8")
    FlowDir_Fill1.save(output_gdb + '\\flowdir')

    print("FlowAccumulation")
    FlowAcc_Flow1 = arcpy.sa.FlowAccumulation(in_flow_direction_raster=output_gdb + '\\flowdir', in_weight_raster="", data_type="FLOAT", flow_direction_type="D8")
    FlowAcc_Flow1.save(output_gdb + '\\flowacc')

    print("GreaterThan")
    flowfilter = output_gdb + "\\Greater_flow1"
    Greater_Than = flowfilter
    ### in_raster_or_constant2 may need to be changed based on the area sampled
    flowfilter = arcpy.sa.GreaterThan(in_raster_or_constant1=output_gdb + '\\flowacc', in_raster_or_constant2=5000)
    flowfilter.save(Greater_Than)

    print("RasterToPolyline")
    arcpy.conversion.RasterToPolyline(in_raster=flowfilter, out_polyline_features=output_gdb + '\\flowlines', background_value="ZERO", minimum_dangle_length=0, simplify="SIMPLIFY", raster_field="Value")

    ### Throw away any streams created that lay in a known waterbody
    print("Erase")
    arcpy.analysis.Erase(in_features=output_gdb + '\\flowlines', erase_features=data + "waterbodies", out_feature_class=output_gdb + '\\streams', cluster_tolerance="")


def make_waterfall_points(polyline):
    
    print("make_waterfall_points")
    spatial_ref = arcpy.Describe(polyline).spatialReference

    ### Make a featureclass to hold the waterfall points
    waterfall_point_fl = arcpy.CreateFeatureclass_management(output_gdb, "waterfallpoints",  "POINT", "", "DISABLED", "DISABLED", spatial_ref)
    arcpy.AddField_management(waterfall_point_fl, "x", "FLOAT")
    arcpy.AddField_management(waterfall_point_fl, "y", "FLOAT")
    arcpy.AddField_management(waterfall_point_fl, "height", "FLOAT")
    

    search_fields = ["SHAPE@", "OID@"]
    insert_fields = ["SHAPE@", "LineOID", "Value"]

    ### Loop thru the stream lines and place a point every 'reach_distance' distance
    with arcpy.da.SearchCursor(polyline, (search_fields)) as search:


            for row in search:
                i = 0
                
                    
                line_geom = row[0]
                length = float(line_geom.length)
                count = float(reach_distance)
                oid = str(row[1])
                start = arcpy.PointGeometry(line_geom.firstPoint)
                end = arcpy.PointGeometry(line_geom.lastPoint)

                ### Make all of the intermediate featureclass in_memory.  Its much quicker as they dont write to disk and we dont need them anyway
                mem_point = arcpy.CreateFeatureclass_management("in_memory", "mem_point", "POINT", "", "DISABLED", "DISABLED", spatial_ref)
                arcpy.AddField_management(mem_point, "LineOID", "LONG")
                arcpy.AddField_management(mem_point, "Value", "FLOAT")
  


                # dt_start = datetime.now()
                with arcpy.da.InsertCursor(mem_point, (insert_fields)) as insert:
                    while count <= length:
                        point = line_geom.positionAlongLine(count, False)
                        insert.insertRow((point, oid, count))
                        count += float(reach_distance)

                mem_point_fl = arcpy.MakeFeatureLayer_management(mem_point, "Points_memory")

                ### Get elevation values for the point set from the DEM
                arcpy.gp.ExtractValuesToPoints_sa(mem_point_fl, dem_extract, "in_memory\\pointvals", "NONE", "VALUE_ONLY")
                arcpy.conversion.FeatureClassToFeatureClass("in_memory\\pointvals", output_gdb, "streampoints") 

                lstrows = []
                with arcpy.da.SearchCursor("in_memory\\pointvals", (["RASTERVALU","SHAPE@XY"])) as tblcursor:
                    for row in tblcursor:
                        height = row[0]
                        x, y = row[1]
                        lstrows.append(row)
                        

                arcpy.Delete_management("in_memory\\pointvals")
                arcpy.Delete_management(mem_point_fl) 
                

                ###  Only insert waterfall points that meet the height requirement
                insert_fields_waterfall = ["SHAPE@", "x", "y", "height"]
                with arcpy.da.InsertCursor(waterfall_point_fl, (insert_fields_waterfall)) as insert_waterfall:
                    for k in range(1, len(lstrows)):
                        diff = (lstrows[k][0])- (lstrows[k-1][0])

                        if(abs(diff) > float(height_filter)):

                            x, y = lstrows[k][1]
                            height = abs(diff)

                            pt = arcpy.Point(x,y)
                            pt_geometry = arcpy.PointGeometry(pt, spatial_ref)

                            insert_waterfall.insertRow((pt_geometry, x, y, height))


                        
                arcpy.Delete_management(mem_point)

                i = i + 1


def watershed_filter():

    print("Derive waterfall watersheds")
    Watersh_flow2 = arcpy.sa.Watershed(in_flow_direction_raster=output_gdb + '\\flowdir', in_pour_point_data=output_gdb + '\\waterfallpoints', pour_point_field="OBJECTID")
    Watersh_flow2.save(output_gdb + "\\watersheds")

    print("Convert watersheds to polygons")
    arcpy.conversion.RasterToPolygon(in_raster=output_gdb + "\\watersheds", out_polygon_features=output_gdb + "\\watershedpolys", simplify="SIMPLIFY", raster_field="Value", create_multipart_features="SINGLE_OUTER_PART", max_vertices_per_feature=None)

    print("Calculate Acres")
    watershedpolys = arcpy.management.CalculateGeometryAttributes(in_features=output_gdb + "\\watershedpolys", geometry_property=[["acres", "AREA_GEODESIC"]], length_unit="", area_unit="ACRES_US", coordinate_system="PROJCS[\"NAD_1983_StatePlane_Kentucky_FIPS_1600_Feet\",GEOGCS[\"GCS_North_American_1983\",DATUM[\"D_North_American_1983\",SPHEROID[\"GRS_1980\",6378137.0,298.257222101]],PRIMEM[\"Greenwich\",0.0],UNIT[\"Degree\",0.0174532925199433]],PROJECTION[\"Lambert_Conformal_Conic\"],PARAMETER[\"False_Easting\",4921250.0],PARAMETER[\"False_Northing\",3280833.333333333],PARAMETER[\"Central_Meridian\",-85.75],PARAMETER[\"Standard_Parallel_1\",37.08333333333334],PARAMETER[\"Standard_Parallel_2\",38.66666666666666],PARAMETER[\"Latitude_Of_Origin\",36.33333333333334],UNIT[\"Foot_US\",0.3048006096012192]]", coordinate_format="SAME_AS_INPUT")[0]

    print("Filter out watersheds less than <<watershed_acreage_filter>> acres")
    lst_gridcodes = []
    with arcpy.da.UpdateCursor(output_gdb + "\\watershedpolys", ["acres","gridcode"]) as cursor:
        for row in cursor:
            gridcode = row[1]
            if (row[0] < float(watershed_acreage_filter)):
                lst_gridcodes.append(gridcode)
                cursor.deleteRow()

    print(lst_gridcodes)
    with arcpy.da.UpdateCursor(output_gdb + "\\waterfallpoints", ["OID@"]) as cursor:
        for row in cursor:
            oid = row[0]
            if (oid in lst_gridcodes):
                print("OID: " + str(oid))
                cursor.deleteRow()


    print("Make lat/lng coordinate field")
    waterfalls = arcpy.management.CalculateGeometryAttributes(in_features=output_gdb + '\\waterfallpoints', geometry_property=[["lat", "POINT_Y"], ["lng", "POINT_X"]], length_unit="", area_unit="", coordinate_system="GEOGCS[\"GCS_WGS_1984\",DATUM[\"D_WGS_1984\",SPHEROID[\"WGS_1984\",6378137.0,298.257223563]],PRIMEM[\"Greenwich\",0.0],UNIT[\"Degree\",0.0174532925199433]]", coordinate_format="DD")[0]


if __name__ == '__main__':    
        
    ### Make a scratch folder and scratch geodatabase
    PrepareWorkspace()
     
    ### Derive a stream network from the DEM
    DeriveSteams()

    ### Make waterfalls points that meet the height filter.
    make_waterfall_points(output_gdb + '\\streams')

    watershed_filter()

