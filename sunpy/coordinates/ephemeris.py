# -*- coding: utf-8 -*-
"""
Ephemeris calculations using SunPy coordinate frames
"""
# Skip checking the __all__ here as we are making deprecated versions
# flake8: noqa F822

import datetime
import warnings

import numpy as np
import astropy.units as u
from astropy.time import Time
from astropy.coordinates import (SkyCoord, Angle, Longitude, Distance,
                                 ICRS, ITRS, AltAz,
                                 get_body_barycentric)
from astropy.coordinates.representation import CartesianRepresentation, SphericalRepresentation
from astropy._erfa.core import ErfaWarning
from astropy.constants import c as speed_of_light
# Versions of Astropy that do not have HeliocentricMeanEcliptic have the same frame
# with the misleading name HeliocentricTrueEcliptic
try:
    from astropy.coordinates import HeliocentricMeanEcliptic
except ImportError:
    from astropy.coordinates import HeliocentricTrueEcliptic as HeliocentricMeanEcliptic
from astropy.coordinates import HeliocentricEclipticIAU76

from sunpy.time import parse_time
from sunpy import log
from sunpy.sun.constants import radius as _RSUN
from sunpy.util.decorators import add_common_docstring, deprecated
from sunpy.time.time import _variables_for_parse_time_docstring

from .frames import HeliographicStonyhurst as HGS
from .transformations import _SUN_DETILT_MATRIX, _SOLAR_NORTH_POLE_HCRS

__author__ = "Albert Y. Shih"
__email__ = "ayshih@gmail.com"

__all__ = ['get_body_heliographic_stonyhurst', 'get_earth',
           'get_sun_B0', 'get_sun_L0', 'get_sun_P', 'get_sunearth_distance',
           'get_sun_orientation', 'get_horizons_coord']


@add_common_docstring(**_variables_for_parse_time_docstring())
def get_body_heliographic_stonyhurst(body, time='now', observer=None):
    """
    Return a `~sunpy.coordinates.frames.HeliographicStonyhurst` frame for the location of a
    solar-system body at a specified time.  The location can be corrected for light travel time
    to an observer.

    Parameters
    ----------
    body : `str`
        The solar-system body for which to calculate positions
    time : {parse_time_types}
        Time to use in a parse_time-compatible format
    observer : `~astropy.coordinates.SkyCoord`
        If None, the returned coordinate is the instantaneous or "true" location.
        If not None, the returned coordinate is the astrometric location (i.e., accounts for light
        travel time to the specified observer)

    Returns
    -------
    out : `~sunpy.coordinates.frames.HeliographicStonyhurst`
        Location of the solar-system body in the `~sunpy.coordinates.HeliographicStonyhurst` frame

    Notes
    -----
    There is no correction for aberration due to observer motion.  For a body close to the Sun in
    angular direction relative to the observer, the correction can be negligible because the
    apparent location of the body will shift in tandem with the Sun.
    """
    obstime = parse_time(time)

    if observer is None:
        body_icrs = get_body_barycentric(body, obstime)
    else:
        observer_icrs = SkyCoord(observer).icrs.cartesian

        # This implementation is modeled after Astropy's `_get_apparent_body_position`
        light_travel_time = 0.*u.s
        emitted_time = obstime
        delta_light_travel_time = 1.*u.s  # placeholder value
        while np.any(np.fabs(delta_light_travel_time) > 1.0e-8*u.s):
            body_icrs = get_body_barycentric(body, emitted_time)
            distance = (body_icrs - observer_icrs).norm()
            delta_light_travel_time = light_travel_time - distance / speed_of_light
            light_travel_time = distance / speed_of_light
            emitted_time = obstime - light_travel_time

        log.info(f"Apparent body location accounts for {light_travel_time.to('s').value:.2f}"
                 " seconds of light travel time")

    body_hgs = ICRS(body_icrs).transform_to(HGS(obstime=obstime))

    return body_hgs


@add_common_docstring(**_variables_for_parse_time_docstring())
def get_earth(time='now'):
    """
    Return a `~astropy.coordinates.SkyCoord` for the location of the Earth at a specified time in
    the `~sunpy.coordinates.frames.HeliographicStonyhurst` frame.  The longitude will be 0 by definition.

    Parameters
    ----------
    time : {parse_time_types}
        Time to use in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.SkyCoord`
        Location of the Earth in the `~sunpy.coordinates.frames.HeliographicStonyhurst` frame
    """
    earth = get_body_heliographic_stonyhurst('earth', time=time)

    # Explicitly set the longitude to 0
    earth = SkyCoord(0*u.deg, earth.lat, earth.radius, frame=earth)

    return earth


@add_common_docstring(**_variables_for_parse_time_docstring())
def get_horizons_coord(body, time='now', id_type='majorbody'):
    """
    Queries JPL HORIZONS and returns a `~astropy.coordinates.SkyCoord` for the location of a
    solar-system body at a specified time.  This location is the instantaneous or "true" location,
    and is not corrected for light travel time or observer motion.

    .. note::
        This function requires the Astroquery package to be installed and
        requires an Internet connection.

    Parameters
    ----------
    body : `str`
        The solar-system body for which to calculate positions.  One can also use the search form
        linked below to find valid names or ID numbers.
    id_type : `str`
        If 'majorbody', search by name for planets, satellites, or other major bodies.
        If 'smallbody', search by name for asteroids or comets.
        If 'id', search by ID number.
    time : {parse_time_types}
        Time to use in a parse_time-compatible format

    Returns
    -------
    `~astropy.coordinates.SkyCoord`
        Location of the solar-system body

    Notes
    -----
    Be aware that there can be discrepancies between the coordinates returned by JPL HORIZONS,
    the coordinates reported in mission data files, and the coordinates returned by
    `~sunpy.coordinates.get_body_heliographic_stonyhurst`.

    References
    ----------
    * `JPL HORIZONS <https://ssd.jpl.nasa.gov/?horizons>`_
    * `JPL HORIZONS form to search bodies <https://ssd.jpl.nasa.gov/horizons.cgi?s_target=1#top>`_
    * `Astroquery <https://astroquery.readthedocs.io/en/latest/>`_

    Examples
    --------
    >>> from sunpy.coordinates import get_horizons_coord

    Query the location of Venus

    >>> get_horizons_coord('Venus barycenter', '2001-02-03 04:05:06')  # doctest: +REMOTE_DATA
    INFO: Obtained JPL HORIZONS location for Venus Barycenter (2) [sunpy.coordinates.ephemeris]
    <SkyCoord (HeliographicStonyhurst: obstime=2001-02-03T04:05:06.000): (lon, lat, radius) in (deg, deg, AU)
        (-33.93155836, -1.64998443, 0.71915147)>

    Query the location of the SDO spacecraft

    >>> get_horizons_coord('SDO', '2011-11-11 11:11:11')  # doctest: +REMOTE_DATA
    INFO: Obtained JPL HORIZONS location for Solar Dynamics Observatory (spac [sunpy.coordinates.ephemeris]
    <SkyCoord (HeliographicStonyhurst: obstime=2011-11-11T11:11:11.000): (lon, lat, radius) in (deg, deg, AU)
        (0.01019118, 3.29640728, 0.99011042)>

    Query the location of the SOHO spacecraft via its ID number (-21)

    >>> get_horizons_coord(-21, '2004-05-06 11:22:33', 'id')  # doctest: +REMOTE_DATA
    INFO: Obtained JPL HORIZONS location for SOHO (spacecraft) (-21) [sunpy.coordinates.ephemeris]
    <SkyCoord (HeliographicStonyhurst: obstime=2004-05-06T11:22:33.000): (lon, lat, radius) in (deg, deg, AU)
        (0.25234902, -3.55863633, 0.99923086)>
    """
    obstime = parse_time(time)
    array_time = np.reshape(obstime, (-1,))  # Convert to an array, even if scalar

    # Import here so that astroquery is not a module-level dependency
    from astroquery.jplhorizons import Horizons
    query = Horizons(id=body, id_type=id_type,
                     location='500@10',      # Heliocentric (mean ecliptic)
                     epochs=array_time.tdb.jd.tolist())  # Time must be provided in JD TDB
    try:
        result = query.vectors()
    except Exception:  # Catch and re-raise all exceptions, and also provide query URL if generated
        if query.uri is not None:
            log.error(f"See the raw output from the JPL HORIZONS query at {query.uri}")
        raise
    log.info(f"Obtained JPL HORIZONS location for {result[0]['targetname']}")
    log.debug(f"See the raw output from the JPL HORIZONS query at {query.uri}")

    # JPL HORIZONS results are sorted by observation time, so this sorting needs to be undone.
    # Calling argsort() on an array returns the sequence of indices of the unsorted list to put the
    # list in order.  Calling argsort() again on the output of argsort() reverses the mapping:
    # the output is the sequence of indices of the sorted list to put that list back in the
    # original unsorted order.
    unsorted_indices = obstime.argsort().argsort()
    result = result[unsorted_indices]

    vector = CartesianRepresentation(result['x'], result['y'], result['z'])
    coord = SkyCoord(vector, frame=HeliocentricEclipticIAU76, obstime=obstime)

    return coord.transform_to(HGS).reshape(obstime.shape)


# The code beyond this point should be moved to sunpy.coordinates.sun after the deprecation period

@add_common_docstring(**_variables_for_parse_time_docstring())
def _B0(time='now'):
    """
    Return the B0 angle for the Sun at a specified time, which is the heliographic latitude of the
    of the center of the disk of the Sun as seen from Earth. The range of B0 is +/-7.23 degrees.

    Equivalent definitions include:
        * The heliographic latitude of Earth
        * The tilt of the solar North rotational axis toward Earth


    Parameters
    ----------
    time : {parse_time_types}
        Time to use in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Angle`
        The position angle
    """
    return Angle(get_earth(time).lat)


# Function returns a SkyCoord's longitude in the de-tilted frame (HCRS rotated so that the Sun's
# rotation axis is aligned with the Z axis)
def _detilt_lon(coord):
    coord_detilt = coord.hcrs.cartesian.transform(_SUN_DETILT_MATRIX)
    return coord_detilt.represent_as(SphericalRepresentation).lon.to('deg')


# J2000.0 epoch
_J2000 = Time('J2000.0', scale='tt')


# One of the two nodes of intersection between the ICRF equator and Sun's equator in HCRS
_NODE = SkyCoord(_SOLAR_NORTH_POLE_HCRS.lon + 90*u.deg, 0*u.deg, frame='hcrs')


# The longitude in the de-tilted frame of the Sun's prime meridian.
# The IAU (Seidelmann et al. 2007 and later) defines the true longitude of the meridian (i.e.,
# without light travel time to Earth and aberration effects) as 84.176 degrees eastward at J2000.
_DLON_MERIDIAN = Longitude(_detilt_lon(_NODE) + 84.176*u.deg)


@add_common_docstring(**_variables_for_parse_time_docstring())
def _L0(time='now',
        light_travel_time_correction=True,
        nearest_point=True,
        aberration_correction=False):
    """
    Return the L0 angle for the Sun at a specified time, which is the apparent Carrington longitude
    of the Sun-disk center as seen from Earth.

    Observer corrections can be disabled, and then this function will instead return the true
    Carrington longitude.

    Parameters
    ----------
    time : {parse_time_types}
        Time to use in a parse_time-compatible format
    light_travel_time_correction : `bool`
        If True, apply the correction for light travel time from Sun to Earth.  Defaults to True.
    nearest_point : `bool`
        If True, calculate the light travel time to the nearest point on the Sun's surface rather
        than the light travel time to the center of the Sun (i.e., a difference of the solar
        radius).  Defaults to True.
    aberration_correction : `bool`
        If True, apply the stellar-aberration correction due to Earth's motion.  Defaults to False.

    Returns
    -------
    `~astropy.coordinates.Longitude`
        The Carrington longitude

    Notes
    -----
    This longitude is calculated using current IAU values (Seidelmann et al. 2007 and later), which
    do not include the effects of light travel time and aberration due to Earth's motion (see that
    paper's Appendix).  This function then, by default, applies the light-travel-time correction
    for the nearest point on the Sun's surface, but does not apply the stellar-aberration correction
    due to Earth's motion.

    We do not apply the stellar-abberation correction by default because it should not be applied
    for purposes such as co-aligning images that are each referenced to Sun-disk center.  Stellar
    aberration does not shift the apparent positions of solar features relative to the Sun-disk
    center.

    The Astronomical Almanac applies the stellar-aberration correction in their printed published
    L0 values (see also Urban & Kaplan 2007).  Applying the stellar-aberration correction due to
    Earth's motion decreases the apparent Carrington longitude by ~20.5 arcseconds.

    References
    ----------
    * Seidelmann et al. (2007), "Report of the IAU/IAG Working Group on cartographic coordinates
      and rotational elements: 2006" `(link) <http://dx.doi.org/10.1007/s10569-007-9072-y>`__
    * Urban & Kaplan (2007), "Investigation of Change in the Computational Technique of the Sun's
      Physical Ephemeris in The Astronomical Almanac"
      `(link) <http://asa.hmnao.com/static/files/sun_rotation_change.pdf>`__
    """
    obstime = parse_time(time)
    earth = get_earth(obstime)

    # Calculate the de-tilt longitude of the Earth
    dlon_earth = _detilt_lon(earth)

    # Calculate the distance to the nearest point on the Sun's surface
    distance = earth.radius - _RSUN if nearest_point else earth.radius

    # Apply a correction for aberration due to Earth motion
    # This expression is an approximation to reduce computations (e.g., it does not account for the
    # inclination of the Sun's rotation axis relative to the ecliptic), but the estimated error is
    # <0.2 arcseconds
    if aberration_correction:
        dlon_earth -= 20.496*u.arcsec * 1*u.AU / earth.radius

    # Antedate the observation time to account for light travel time for the Sun-Earth distance
    antetime = (obstime - distance / speed_of_light) if light_travel_time_correction else obstime

    # Calculate the de-tilt longitude of the meridian due to the Sun's sidereal rotation
    dlon_meridian = Longitude(_DLON_MERIDIAN + (antetime - _J2000) * 14.1844*u.deg/u.day)

    return Longitude(dlon_earth - dlon_meridian)


@add_common_docstring(**_variables_for_parse_time_docstring())
def _P(time='now'):
    """
    Return the position (P) angle for the Sun at a specified time, which is the angle between
    geocentric north and solar north as seen from Earth, measured eastward from geocentric north.
    The range of P is +/-26.3 degrees.

    Parameters
    ----------
    time : {parse_time_types}
        Time to use in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Angle`
        The position angle
    """
    obstime = parse_time(time)

    # Define the frame where its Z axis is aligned with geocentric north
    geocentric = ITRS(obstime=obstime)

    return _sun_north_angle_to_z(geocentric)


@add_common_docstring(**_variables_for_parse_time_docstring())
def _earth_distance(time='now'):
    """
    Return the distance between the Sun and the Earth at a specified time.

    Parameters
    ----------
    time : {parse_time_types}
        Time to use in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Distance`
        The Sun-Earth distance
    """
    obstime = parse_time(time)
    vector = get_body_barycentric('earth', obstime) - get_body_barycentric('sun', obstime)
    return Distance(vector.norm())


@add_common_docstring(**_variables_for_parse_time_docstring())
def _orientation(location, time='now'):
    """
    Return the orientation angle for the Sun from a specified Earth location and time.  The
    orientation angle is the angle between local zenith and solar north, measured eastward from
    local zenith.

    Parameters
    ----------
    location : `~astropy.coordinates.EarthLocation`
        Observer location on Earth
    time : {parse_time_types}
        Time to use in a parse_time-compatible format

    Returns
    -------
    out : `~astropy.coordinates.Angle`
        The orientation of the Sun
    """
    obstime = parse_time(time)

    # Define the frame where its Z axis is aligned with local zenith
    local_frame = AltAz(obstime=obstime, location=location)

    return _sun_north_angle_to_z(local_frame)


def _sun_north_angle_to_z(frame):
    """
    Return the angle between solar north and the Z axis of the provided frame's coordinate system
    and observation time.
    """
    # Find the Sun center in HGS at the frame's observation time(s)
    sun_center_repr = SphericalRepresentation(0*u.deg, 0*u.deg, 0*u.km)
    # The representation is repeated for as many times as are in obstime prior to transformation
    sun_center = SkyCoord(sun_center_repr._apply('repeat', frame.obstime.size),
                          frame=HGS, obstime=frame.obstime)

    # Find the Sun north in HGS at the frame's observation time(s)
    # Only a rough value of the solar radius is needed here because, after the cross product,
    #   only the direction from the Sun center to the Sun north pole matters
    sun_north_repr = SphericalRepresentation(0*u.deg, 90*u.deg, 690000*u.km)
    # The representation is repeated for as many times as are in obstime prior to transformation
    sun_north = SkyCoord(sun_north_repr._apply('repeat', frame.obstime.size),
                         frame=HGS, obstime=frame.obstime)

    # Find the Sun center and Sun north in the frame's coordinate system
    sky_normal = sun_center.transform_to(frame).data.to_cartesian()
    sun_north = sun_north.transform_to(frame).data.to_cartesian()

    # Use cross products to obtain the sky projections of the two vectors (rotated by 90 deg)
    sun_north_in_sky = sun_north.cross(sky_normal)
    z_in_sky = CartesianRepresentation(0, 0, 1).cross(sky_normal)

    # Normalize directional vectors
    sky_normal /= sky_normal.norm()
    sun_north_in_sky /= sun_north_in_sky.norm()
    z_in_sky /= z_in_sky.norm()

    # Calculate the signed angle between the two projected vectors
    cos_theta = sun_north_in_sky.dot(z_in_sky)
    sin_theta = sun_north_in_sky.cross(z_in_sky).dot(sky_normal)
    angle = np.arctan2(sin_theta, cos_theta).to('deg')

    # If there is only one time, this function's output should be scalar rather than array
    if angle.size == 1:
        angle = angle[0]

    return Angle(angle)


# The following functions are moved in the API to sunpy.coordinates.sun and renamed
_old_names = ['get_sun_B0', 'get_sun_L0', 'get_sun_P', 'get_sunearth_distance',
              'get_sun_orientation']
_new_module = 'sunpy.coordinates.sun.'
_new_names = ['B0', 'L0', 'P', 'earth_distance', 'orientation']

# Create a deprecation hook for each of the functions
# Note that the code for each of these functions is still in this module as a private function
for old, new in zip(_old_names, _new_names):
    vars()[old] = deprecated('1.0', name=old, alternative=_new_module + new)(vars()['_' + new])
